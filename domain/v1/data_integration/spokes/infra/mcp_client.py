"""MCP 클라이언트 - MCP 서버 연결 및 Tool 로드 관리"""
from __future__ import annotations

import builtins
import inspect
import os
import sys
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, List, Optional, Union
from loguru import logger

from backend.core.config.settings import get_settings

from .path_resolver import find_repo_root

try:
    from langchain_core.tools import BaseTool, StructuredTool
    from pydantic import BaseModel, Field, field_validator

    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    BaseTool = Any
    BaseModel = Any  # type: ignore[misc, assignment]
    Field = None  # type: ignore[misc, assignment]
    StructuredTool = Any  # type: ignore[misc, assignment]


# Tool 서버 경로: data_integration 전용 SR 서버는 infra, 나머지는 shared/tool
_INFRA_DIR = Path(__file__).resolve().parent
_REPO_ROOT = find_repo_root(Path(__file__))
_TOOL_DIR = _REPO_ROOT / "backend" / "domain" / "shared" / "tool"
_SR_SERVERS_IN_INFRA = {"sr_tools", "sr_index_tools", "sr_body_tools", "sr_images_tools"}
_INPROCESS_ELIGIBLE_SERVERS = {"sr_tools", "sr_index_tools", "sr_body_tools", "sr_images_tools"}

# Streamable HTTP: 기본은 `get_settings()`(.env 반영), 런타임에만 바뀌는 값은 os.environ 우선
# (예: api `data_integration/main.py` lifespan 이 MCP_SR_INDEX_TOOLS_URL 을 주입).
_MCP_STREAMABLE_HTTP_SERVERS = frozenset(
    {"sr_index_tools", "sr_tools", "sr_body_tools", "sr_images_tools", "web_search"}
)
_MCP_SERVER_ENV_KEYS: dict[str, str] = {
    "sr_index_tools": "MCP_SR_INDEX_TOOLS_URL",
    "sr_tools": "MCP_SR_TOOLS_URL",
    "sr_body_tools": "MCP_SR_BODY_TOOLS_URL",
    "sr_images_tools": "MCP_SR_IMAGES_TOOLS_URL",
    "web_search": "MCP_WEB_SEARCH_URL",
}


def _remote_url_from_settings(server_name: str) -> str:
    if server_name not in _MCP_STREAMABLE_HTTP_SERVERS:
        return ""
    env_key = _MCP_SERVER_ENV_KEYS.get(server_name)
    if env_key:
        live = os.environ.get(env_key, "").strip()
        if live:
            return live
    s = get_settings()
    mapping: dict[str, str] = {
        "sr_index_tools": s.mcp_sr_index_tools_url,
        "sr_tools": s.mcp_sr_tools_url,
        "sr_body_tools": s.mcp_sr_body_tools_url,
        "sr_images_tools": s.mcp_sr_images_tools_url,
        "web_search": s.mcp_web_search_url,
    }
    return (mapping.get(server_name) or "").strip()


# Python 3.11+ TaskGroup 실패 등 (except Exception 에 안 잡힘)
# ExceptionGroup 만이 아니라 BaseExceptionGroup 으로 잡아 타입/백포트 차이를 흡수
_BASE_EXCEPTION_GROUP_TYPE = getattr(builtins, "BaseExceptionGroup", None)


class _MCPPassThroughTool(BaseTool):
    """LLM 인자를 검증/변형 없이 MCP call_tool에 그대로 넘기는 도구."""
    session: Any = None
    tool_name: str = ""

    def _parse_input(self, tool_input: Any, tool_call_id: Any = None) -> Any:
        if isinstance(tool_input, dict):
            return dict(tool_input)
        return tool_input

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("MCP 도구는 async만 지원")

    async def _arun(self, *args: Any, **kwargs: Any) -> Any:
        arguments = dict(kwargs)
        for k in ("run_manager", "config"):
            arguments.pop(k, None)
        try:
            out = await self.session.call_tool(self.tool_name, arguments)
        except Exception as e:
            # MCP 전송/프로토콜 오류 시 예외 대신 dict 반환 → 에이전트 루프가 계속 진행
            logger.exception(
                "[MCPClient] call_tool 실패: tool={} arg_keys={} err={}",
                self.tool_name,
                list(arguments.keys()),
                e,
            )
            return {"error": str(e), "results": []}
        if hasattr(out, "content") and out.content:
            for c in out.content:
                if getattr(c, "type", None) == "text":
                    return getattr(c, "text", str(c))
        if isinstance(out, dict):
            return str(out.get("content", out))
        return str(out)


class _InProcessTool:
    """MCP 없이 같은 프로세스에서 직접 함수 실행 (LangChain 미설치·래핑 실패 시 폴백)."""

    def __init__(self, name: str, func: Any):
        self.name = name
        self._func = func

    async def ainvoke(self, arguments: dict) -> Any:
        args = arguments or {}
        if asyncio.iscoroutinefunction(self._func):
            return await self._func(**args)
        return await asyncio.to_thread(self._func, **args)


class _InProcessPassThroughTool(BaseTool):
    """
    LLM 인자를 Pydantic 검증/model_dump() 없이 in-process 함수에 그대로 넘김.
    StructuredTool.from_function은 실행 시 인자가 비는 경우가 있어(data_integration.md 3.1) 사용하지 않음.
    """

    target_fn: Any = Field(default=None, exclude=True)

    def _parse_input(self, tool_input: Any, tool_call_id: Any = None) -> Any:
        if isinstance(tool_input, dict):
            return dict(tool_input)
        return tool_input

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("in-process 도구는 async만 지원")

    async def _arun(self, *args: Any, **kwargs: Any) -> Any:
        arguments = dict(kwargs)
        for k in ("run_manager", "config"):
            arguments.pop(k, None)
        fn = self.target_fn
        if fn is None:
            raise RuntimeError("in-process 도구에 target_fn이 없습니다")
        try:
            sig = inspect.signature(fn)
            allowed = set(sig.parameters.keys())
            filtered = {k: v for k, v in arguments.items() if k in allowed}
        except (TypeError, ValueError):
            filtered = arguments
        if asyncio.iscoroutinefunction(fn):
            return await fn(**filtered)
        return await asyncio.to_thread(fn, **filtered)


def _load_sr_body_tools_with_structured_schema() -> List[Any]:
    """
    ChatOpenAI.bind_tools 등: 일부 LLM/스키마 조합에서 type=array 일 때 `items`가 필요함.
    Pydantic args_schema가 있는 StructuredTool로 등록한다.
    (_InProcessPassThroughTool은 args_schema가 비어 array 스키마가 불완전할 수 있음)
    """
    if not LANGCHAIN_AVAILABLE or Field is None or StructuredTool is None:
        return []

    from backend.domain.shared.tool.sr_report.index.sr_index_agent_tools import get_pdf_metadata
    from backend.domain.shared.tool.parsing.body_parser import parse_body_pages
    from backend.domain.shared.tool.sr_report.body import map_body_pages_to_sr_report_body
    from backend.domain.shared.tool.sr_report.save.sr_save_tools import save_sr_report_body_batch

    class GetPdfMetadataInput(BaseModel):
        report_id: str = Field(description="historical_sr_reports.id (UUID 문자열)")

    class ParseBodyPagesInput(BaseModel):
        pdf_bytes_b64: str = Field(description="PDF 바이너리의 base64 문자열")
        pages: list[int] = Field(description="추출할 페이지 번호 목록 (1-based)")

    class MapBodyPagesInput(BaseModel):
        """parse_body_pages는 body_by_page 키를 int로 반환할 수 있어, 검증 전 str 키로 정규화."""

        body_by_page: dict[str, str] = Field(
            description="페이지 번호(문자열 키) → 해당 페이지 본문 텍스트",
        )
        report_id: str = Field(description="historical_sr_reports.id (UUID)")
        index_page_numbers: Optional[list[int]] = Field(
            default=None,
            description="인덱스 페이지 번호 목록(없으면 빈 리스트로 처리)",
        )
        use_llm_toc_align: bool = Field(
            default=False,
            description=(
                "호환용 옵션(현재 미사용). "
                "toc_path는 페이지 상단 제목 기반으로 생성됨"
            ),
        )
        openai_api_key: Optional[str] = Field(
            default=None,
            description="OpenAI API 키(없으면 OPENAI_API_KEY 환경 변수)",
        )
        llm_model: Optional[str] = Field(
            default=None,
            description="호환용 옵션(현재 미사용)",
        )

        @field_validator("body_by_page", mode="before")
        @classmethod
        def _normalize_body_by_page_keys(cls, v: Any) -> dict[str, str]:
            if v is None:
                return {}
            if not isinstance(v, dict):
                raise TypeError("body_by_page는 페이지→텍스트 dict 여야 합니다")
            out: dict[str, str] = {}
            for k, val in v.items():
                key = k if isinstance(k, str) else str(k)
                if val is None:
                    out[key] = ""
                elif isinstance(val, str):
                    out[key] = val
                else:
                    out[key] = str(val)
            return out

    class SaveBodyBatchInput(BaseModel):
        report_id: str = Field(description="historical_sr_reports.id")
        bodies: list[dict[str, Any]] = Field(
            description=(
                "sr_report_body 배치 저장용 행 목록: page_number, content_text 필수; "
                "is_index_page, content_type, paragraphs, toc_path(문자열 배열 JSON 목차 경로) 선택"
            ),
        )

    def _map_body_wrapper(
        body_by_page: dict[str, str],
        report_id: str,
        index_page_numbers: Optional[list[int]] = None,
        use_llm_toc_align: bool = False,
        openai_api_key: Optional[str] = None,
        llm_model: Optional[str] = None,
    ) -> Any:
        # 매핑 함수는 int/str 키 모두 허용
        raw: dict[Any, str] = {k: v for k, v in body_by_page.items()}
        return map_body_pages_to_sr_report_body(
            raw,
            report_id,
            index_page_numbers if index_page_numbers is not None else [],
            use_llm_toc_align=use_llm_toc_align,
            openai_api_key=openai_api_key,
            llm_model=llm_model,
        )

    return [
        StructuredTool.from_function(
            name="get_pdf_metadata_tool",
            description="DB에서 SR 보고서 메타데이터(total_pages, index_page_numbers, report_name, report_year)를 조회합니다.",
            func=get_pdf_metadata,
            args_schema=GetPdfMetadataInput,
        ),
        StructuredTool.from_function(
            name="parse_body_pages_tool",
            description="PDF에서 지정 페이지 본문 텍스트 추출(Docling→LlamaParse→PyMuPDF).",
            func=parse_body_pages,
            args_schema=ParseBodyPagesInput,
        ),
        StructuredTool.from_function(
            name="map_body_pages_to_sr_report_body_tool",
            description="페이지별 텍스트를 sr_report_body 저장용 행 리스트로 변환합니다.",
            func=_map_body_wrapper,
            args_schema=MapBodyPagesInput,
        ),
        StructuredTool.from_function(
            name="save_sr_report_body_batch_tool",
            description="sr_report_body 테이블에 본문을 배치 저장합니다.",
            func=save_sr_report_body_batch,
            args_schema=SaveBodyBatchInput,
        ),
    ]


def _wrap_inprocess_tool(name: str, func: Any, description: str) -> Any:
    """
    ChatGroq.bind_tools 호환 BaseTool + 실행 시 LLM 인자 손실 없이 in-process 호출.
    """
    if not LANGCHAIN_AVAILABLE or Field is None:
        return _InProcessTool(name, func)
    try:
        return _InProcessPassThroughTool(
            name=name,
            description=description,
            target_fn=func,
        )
    except Exception as e:
        logger.warning(
            "[MCPClient] _InProcessPassThroughTool 생성 실패({}), 레거시 _InProcessTool 사용: {}",
            name,
            e,
        )
        return _InProcessTool(name, func)


class MCPClient:
    """MCP 서버 연결 및 Tool 로드를 담당하는 클라이언트"""
    
    def __init__(self):
        self.tool_dir = _TOOL_DIR
        self.infra_dir = _INFRA_DIR
    
    def _get_server_path(self, name: str) -> Path:
        """Tool 서버 스크립트 경로 반환. sr_tools, sr_index_tools, sr_body_tools는 infra, 나머지는 shared/tool."""
        if name in _SR_SERVERS_IN_INFRA:
            return self.infra_dir / f"{name}_server.py"
        return self.tool_dir / f"{name}_server.py"

    def _has_remote_url(self, server_name: str) -> bool:
        return bool(_remote_url_from_settings(server_name))

    def should_use_inprocess(self, server_name: str) -> bool:
        """
        내부 서비스 도구는 URL 미설정 시 in-process를 기본 사용.
        - URL이 설정되어 있으면 외부 통합(HTTP) 우선
        - MCP_INTERNAL_TRANSPORT=stdio 로 강제 시 in-process 비활성화
        """
        policy = get_settings().mcp_internal_transport.strip().lower()
        if policy == "stdio":
            return False
        if server_name not in _INPROCESS_ELIGIBLE_SERVERS:
            return False
        return not self._has_remote_url(server_name)

    async def load_inprocess_tools(self, server_name: str) -> List[Any]:
        """서버 이름에 대응하는 로컬 함수들을 도구 인터페이스로 래핑."""
        if server_name == "sr_tools":
            from .sr_tools_runtime import (
                fetch_page_links,
                download_pdf,
                download_pdf_bytes,
            )
            return [
                _wrap_inprocess_tool(
                    "fetch_page_links",
                    fetch_page_links,
                    "웹 페이지 URL에서 PDF 링크 목록을 추출합니다.",
                ),
                _wrap_inprocess_tool(
                    "download_pdf",
                    download_pdf,
                    "PDF를 지정 경로에 파일로 저장합니다.",
                ),
                _wrap_inprocess_tool(
                    "download_pdf_bytes",
                    download_pdf_bytes,
                    "PDF를 파일로 저장하지 않고 base64 인코딩된 bytes로 다운로드합니다.",
                ),
            ]
        if server_name == "sr_index_tools":
            from backend.domain.shared.tool.sr_report.index.sr_index_agent_tools import (
                get_pdf_metadata,
                inspect_index_pages,
                parse_index_with_docling,
                parse_index_with_llamaparse,
                validate_index_rows,
                detect_anomalies,
                correct_anomalous_rows_with_md,
            )
            return [
                _wrap_inprocess_tool(
                    "get_pdf_metadata_tool",
                    get_pdf_metadata,
                    "DB에서 SR 보고서 메타데이터(총 페이지, 인덱스 페이지 번호 등)를 조회합니다.",
                ),
                _wrap_inprocess_tool(
                    "inspect_index_pages_tool",
                    inspect_index_pages,
                    "인덱스 페이지들의 표 복잡도를 분석합니다.",
                ),
                _wrap_inprocess_tool(
                    "parse_index_with_docling_tool",
                    parse_index_with_docling,
                    "Docling으로 인덱스 페이지를 표로 파싱합니다.",
                ),
                _wrap_inprocess_tool(
                    "parse_index_with_llamaparse_tool",
                    parse_index_with_llamaparse,
                    "LlamaParse로 인덱스 페이지를 마크다운으로 파싱합니다.",
                ),
                _wrap_inprocess_tool(
                    "validate_index_rows_tool",
                    validate_index_rows,
                    "파싱된 인덱스 행을 검증합니다.",
                ),
                _wrap_inprocess_tool(
                    "detect_anomalies_tool",
                    detect_anomalies,
                    "인덱스 데이터 이상치를 탐지합니다.",
                ),
                _wrap_inprocess_tool(
                    "correct_anomalous_rows_with_md_tool",
                    correct_anomalous_rows_with_md,
                    "마크다운을 참고해 이상 행을 보정합니다.",
                ),
            ]
        if server_name == "sr_body_tools":
            structured = _load_sr_body_tools_with_structured_schema()
            if structured:
                return structured
            from backend.domain.shared.tool.sr_report.index.sr_index_agent_tools import get_pdf_metadata
            from backend.domain.shared.tool.parsing.body_parser import parse_body_pages
            from backend.domain.shared.tool.sr_report.body import map_body_pages_to_sr_report_body
            from backend.domain.shared.tool.sr_report.save.sr_save_tools import save_sr_report_body_batch
            return [
                _wrap_inprocess_tool(
                    "get_pdf_metadata_tool",
                    get_pdf_metadata,
                    "DB에서 SR 보고서 메타데이터를 조회합니다.",
                ),
                _wrap_inprocess_tool(
                    "parse_body_pages_tool",
                    parse_body_pages,
                    "본문 페이지 파싱(Docling→LlamaParse→PyMuPDF).",
                ),
                _wrap_inprocess_tool(
                    "map_body_pages_to_sr_report_body_tool",
                    map_body_pages_to_sr_report_body,
                    "파싱 결과를 SR 본문 스키마로 매핑합니다.",
                ),
                _wrap_inprocess_tool(
                    "save_sr_report_body_batch_tool",
                    save_sr_report_body_batch,
                    "본문 데이터를 배치로 저장합니다.",
                ),
            ]
        if server_name == "sr_images_tools":
            import base64
            import json

            from backend.domain.shared.tool.parsing.image_extractor import extract_report_images
            from backend.domain.shared.tool.sr_report.images import map_extracted_images_to_sr_report_rows
            from backend.domain.shared.tool.sr_report.index.sr_index_agent_tools import get_pdf_metadata
            from backend.domain.shared.tool.sr_report.save.sr_save_tools import (
                save_sr_report_images_batch,
            )

            def _get_pdf_metadata_tool(report_id: str) -> str:
                result = get_pdf_metadata(report_id)
                return json.dumps(result, ensure_ascii=False)

            def _extract_report_images_tool(
                pdf_bytes_b64: str,
                pages: list,
                output_dir: str,
                report_id: str,
                index_page_numbers: Optional[list] = None,
            ) -> str:
                pdf_bytes = base64.b64decode(pdf_bytes_b64)
                idx = index_page_numbers if index_page_numbers is not None else []
                result = extract_report_images(
                    pdf_bytes,
                    list(pages),
                    output_dir,
                    report_id,
                    index_page_numbers=idx,
                )
                return json.dumps(result, ensure_ascii=False)

            def _norm_images_by_page(d: Any) -> dict[int, list]:
                out: dict[int, list] = {}
                for k, v in (d or {}).items():
                    try:
                        pk = int(k)
                    except (TypeError, ValueError):
                        continue
                    if isinstance(v, list):
                        out[pk] = v
                return out

            def _map_extracted_images_to_sr_report_rows_tool(
                images_by_page: dict,
                report_id: str,
            ) -> str:
                rows = map_extracted_images_to_sr_report_rows(
                    report_id,
                    _norm_images_by_page(images_by_page),
                )
                return json.dumps(rows, ensure_ascii=False)

            def _save_sr_report_images_batch_tool(
                report_id: str,
                rows: list,
                replace_existing: bool = True,
            ) -> str:
                result = save_sr_report_images_batch(
                    report_id,
                    list(rows),
                    replace_existing=replace_existing,
                )
                return json.dumps(result, ensure_ascii=False)

            return [
                _wrap_inprocess_tool(
                    "get_pdf_metadata_tool",
                    _get_pdf_metadata_tool,
                    "DB에서 SR 보고서 메타데이터를 조회합니다.",
                ),
                _wrap_inprocess_tool(
                    "extract_report_images_tool",
                    _extract_report_images_tool,
                    "PDF에서 지정 페이지 임베디드 이미지를 추출합니다.",
                ),
                _wrap_inprocess_tool(
                    "map_extracted_images_to_sr_report_rows_tool",
                    _map_extracted_images_to_sr_report_rows_tool,
                    "추출 결과를 sr_report_images 저장용 행으로 변환합니다.",
                ),
                _wrap_inprocess_tool(
                    "save_sr_report_images_batch_tool",
                    _save_sr_report_images_batch_tool,
                    "sr_report_images 테이블에 배치 저장합니다.",
                ),
            ]
        return []

    @asynccontextmanager
    async def tool_runtime(self, server_name: str):
        """
        서버 도구 실행 컨텍스트.
        - in-process 정책이면 로컬 도구 리스트만 yield
        - 원격은 **연결·ClientSession을 유지한 채** yield (도구가 session을 참조하므로
          연결을 먼저 닫으면 anyio.ClosedResourceError 발생)
        """
        if self.should_use_inprocess(server_name):
            tools = await self.load_inprocess_tools(server_name)
            logger.info("[MCPClient] {} in-process 도구 사용 ({}개)", server_name, len(tools))
            yield tools
            return

        params = self.get_mcp_params(server_name)
        if not params:
            yield []
            return

        try:
            from mcp import ClientSession
        except ImportError:
            logger.error("mcp 패키지 없음. pip install mcp 필요")
            yield []
            return

        last_error: BaseException | None = None
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                async with self.connect(params) as (read_stream, write_stream):
                    async with ClientSession(read_stream, write_stream) as session:
                        await session.initialize()
                        tools = await self.load_tools_from_session(session, server_name)
                        if not tools:
                            raise RuntimeError(
                                f"{server_name}: MCP 도구 목록이 비어 있습니다."
                            )
                        logger.info(
                            "[MCPClient] {} 원격 MCP 연결 유지·도구 {}개 사용",
                            server_name,
                            len(tools),
                        )
                        # 세션/스트림이 열린 동안만 도구 호출 가능
                        yield tools
                        return
            except BaseException as e:
                if type(e) is GeneratorExit:
                    raise
                if isinstance(e, (KeyboardInterrupt, SystemExit)):
                    raise
                if isinstance(e, asyncio.CancelledError):
                    raise
                if isinstance(e, Exception):
                    last_error = e
                elif _BASE_EXCEPTION_GROUP_TYPE is not None and isinstance(
                    e, _BASE_EXCEPTION_GROUP_TYPE
                ):
                    last_error = e
                else:
                    raise
                if attempt < max_attempts:
                    wait_sec = attempt
                    logger.warning(
                        "[MCPClient] {} 원격 연결 실패({}/{}): {}, {}s 후 재시도",
                        server_name,
                        attempt,
                        max_attempts,
                        e,
                        wait_sec,
                    )
                    await asyncio.sleep(wait_sec)
                    continue
                break
        logger.error("[MCPClient] {} 원격 연결 최종 실패: {}", server_name, last_error)
        yield []
    
    async def load_tools_from_session(
        self, 
        session: Any, 
        server_name: str
    ) -> List[BaseTool]:
        """MCP 세션에서 Tool 목록을 가져와 LangChain Tool로 변환"""
        tools: List[BaseTool] = []
        
        # langchain_mcp_adapters 사용 시도
        try:
            from langchain_mcp_adapters.tools import load_mcp_tools
            tools = await load_mcp_tools(session, server_name=server_name)
            return tools
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"load_mcp_tools 실패 ({server_name}): {e}")
        
        # 수동으로 Tool 래핑
        try:
            list_result = await session.list_tools()
            tool_defs = getattr(list_result, "tools", None) or list_result
            if not tool_defs:
                return []
            
            for t in tool_defs:
                name = getattr(t, "name", None) or (t.get("name") if isinstance(t, dict) else None)
                desc = getattr(t, "description", None) or (t.get("description", "") if isinstance(t, dict) else "")
                if not name:
                    continue
                
                tools.append(
                    _MCPPassThroughTool(
                        session=session,
                        tool_name=name,
                        name=name,
                        description=desc or name,
                    )
                )
        except Exception as e:
            logger.warning(f"MCP list_tools/call_tool 래핑 실패 ({server_name}): {e}")
        
        return tools
    
    def get_mcp_params(self, server_name: str) -> Optional[Union[Any, dict]]:
        """MCP 서버 연결 파라미터 생성.
        - `get_settings()`에 해당 MCP URL이 있으면 Streamable HTTP 연결 정보 반환.
        - 없으면 stdio용 StdioServerParameters 반환.
        """
        url = _remote_url_from_settings(server_name)
        if url:
            return {"transport": "streamable_http", "url": url}

        try:
            from mcp import StdioServerParameters
        except ImportError:
            logger.error("mcp 패키지 없음. pip install mcp 필요")
            return None

        server_path = self._get_server_path(server_name)
        if not server_path.exists():
            logger.error("MCP 서버 스크립트가 없습니다: {}", server_path)
            return None

        try:
            python_exe = sys.executable
            env = os.environ.copy()
            cwd = str(self.infra_dir) if server_name in _SR_SERVERS_IN_INFRA else str(self.tool_dir)
            return StdioServerParameters(
                command=python_exe,
                args=[str(server_path)],
                env=env,
                cwd=cwd,
            )
        except Exception as e:
            logger.error("MCP 파라미터 생성 실패: {}", e)
            return None

    @asynccontextmanager
    async def connect(
        self, params_or_spec: Union[Any, dict]
    ):
        """MCP 서버에 연결하는 비동기 컨텍스트 매니저.
        get_mcp_params() 반환값을 넘기면 stdio 또는 Streamable HTTP 중 적절한 방식으로 연결하고
        (read_stream, write_stream) 을 yield 합니다.
        """
        if isinstance(params_or_spec, dict) and params_or_spec.get("transport") == "streamable_http":
            url = params_or_spec.get("url") or ""
            if not url:
                raise ValueError("streamable_http 지정 시 url 필수")
            try:
                from mcp.client.streamable_http import streamablehttp_client
            except ImportError:
                logger.warning(
                    "mcp.client.streamable_http 없음. pip install mcp 최신 버전 필요."
                )
                raise ValueError(
                    "Streamable HTTP를 사용하려면 mcp 패키지에 streamable_http 클라이언트가 필요합니다."
                ) from None
            async with streamablehttp_client(url=url) as (read_stream, write_stream, *_):
                yield (read_stream, write_stream)
            return

        # stdio
        from mcp.client.stdio import stdio_client
        async with stdio_client(params_or_spec) as (read_stream, write_stream):
            yield (read_stream, write_stream)
