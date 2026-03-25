"""SR Agent - 지속가능경영보고서 검색·다운로드 에이전트

Infra 레이어를 사용하여 실제 에이전트 로직을 실행합니다.
PDF를 bytes로 다운로드하여 반환합니다.
"""
from __future__ import annotations

import asyncio
import base64
import builtins
import json
from typing import Any, Dict, List, Optional
from loguru import logger

from backend.core.config.settings import get_settings

try:
    from langchain_groq import ChatGroq
    from langchain_core.messages import ToolMessage
    from langchain_core.tools import BaseTool
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False

from ..infra.mcp_client import MCPClient
from ..infra.tool_utils import ToolUtils


class SRAgent:
    """
    SR 보고서 검색·다운로드 에이전트
    
    Infra를 사용하여:
    - MCP Tool 로드
    - LLM + Tool 실행
    - PDF bytes 다운로드
    """
    
    def __init__(
        self,
        groq_api_key: Optional[str] = None,
        model_name: str = "llama-3.3-70b-versatile",
        max_iterations: int = 10,
    ):
        if not LANGCHAIN_AVAILABLE:
            raise ImportError("langchain_groq, langchain_core 패키지가 필요합니다.")
        
        self.api_key = groq_api_key or get_settings().groq_api_key
        if not self.api_key:
            raise ValueError("GROQ_API_KEY가 설정되지 않았습니다.")
        
        self.model_name = model_name
        self.max_iterations = max_iterations
        
        self.llm = ChatGroq(model=model_name, api_key=self.api_key, temperature=0)
        
        # Infra 의존성
        self.mcp_client = MCPClient()
        self.tool_utils = ToolUtils()
    
    def build_system_prompt(self, company: str, year: int) -> str:
        """에이전트 시스템 프롬프트 생성 (bytes 모드: download_pdf_bytes 사용)"""
        return f"""당신은 지속가능경영보고서(Sustainability Report/SR/ESG) PDF를 찾아 다운로드하는 에이전트이다.

목표: {company}의 {year}년 지속가능경영보고서 PDF를 bytes로 가져온다. 반드시 한국어(한국판) 보고서를 찾는다.

규칙: 한 번에 반드시 하나의 도구만 호출한다. 도구 결과를 본 뒤 다음 도구를 호출한다.

--- 1단계: 검색 (최초 1회만) ---
tavily_search를 한 번 호출한다. query에는 반드시 한국어/한국판을 의미하는 단어를 포함한다.
- 예: "{company} 지속가능경영보고서 {year} 한국어 PDF" 또는 "{company} sustainability report {year} 한국 PDF" 또는 "{company} ESG report {year} KOR PDF"
- 한국어·한국·KOR·한국어판 등이 쿼리에 들어가야 한다.
검색 결과가 오면 2단계로 간다. 다시 tavily_search를 호출하지 않는다.

--- 2단계: PDF 다운로드 (필수) ---
검색 결과에 [1번 URL에서 추출한 PDF 링크] 목록이 제공된다. 그 목록에서 지속가능경영보고서(sustainability report) 관련 PDF href 하나를 골라 download_pdf_bytes(url=그 href)를 반드시 호출한다.
- 여러 개면 한국어·한국·KOR·한국어판이 제목/URL에 포함된 것을 우선 선택하고, 없으면 첫 번째 또는 sustainability/보고서가 제목에 있는 것을 쓴다.
- fetch_page_links는 호출하지 않는다. 이미 PDF 링크가 추출돼 있다.
- download_pdf_bytes를 사용한다 (파일 저장 없이 bytes 반환).

--- 3단계: 종료 ---
download_pdf_bytes가 success이면 끝낸다. 실패하면 "보고서를 찾을 수 없습니다"라고 보고한다.

최대 {self.max_iterations}번 도구 호출. 검색 후 반드시 download_pdf_bytes를 호출한다.
"""
    
    async def execute(self, company: str, year: int, company_id: Optional[str] = None) -> Dict[str, Any]:
        """
        에이전트 실행 (bytes 모드: PDF bytes 다운로드)
        
        Returns:
            {
                "success": bool,
                "message": str,
                "pdf_bytes": bytes,
                "company": str,
                "year": int,
                "company_id": str
            }
        """
        # 도구 런타임 준비:
        # - web_search: 기본 MCP(원격/stdio)
        # - sr_tools: URL 미설정 시 in-process, 설정 시 원격 MCP
        try:
            async with self.mcp_client.tool_runtime("web_search") as tools1:
                async with self.mcp_client.tool_runtime("sr_tools") as tools2:
                    # Tool 조합 (tavily_search + download_pdf_bytes)
                    all_tools = [t for t in tools1 if t.name == "tavily_search"] + \
                               [t for t in tools2 if t.name in ("download_pdf_bytes", "fetch_page_links")]

                    if not all_tools:
                        return self._error_result("도구를 로드할 수 없습니다. (web_search/sr_tools)")

                    has_tavily = any(t.name == "tavily_search" for t in tools1)
                    if not has_tavily:
                        return self._error_result(
                            "web_search MCP에서 tavily_search를 로드하지 못했습니다. "
                            "MCP_WEB_SEARCH_URL·MCP 서버 기동·네트워크·방화벽을 확인하세요."
                        )

                    logger.info(f"도구 {len(all_tools)}개로 에이전트 실행 (bytes 모드)")

                    # LLM에 Tool 바인딩
                    llm = self.llm.bind_tools(all_tools)

                    # 에이전트 루프 실행
                    return await self._run_loop(company, year, company_id, llm, all_tools)
                            
        except BaseException as e:
            if type(e) is GeneratorExit:
                raise
            if isinstance(e, (KeyboardInterrupt, SystemExit)):
                raise
            if isinstance(e, asyncio.CancelledError):
                raise
            _beg = getattr(builtins, "BaseExceptionGroup", None)
            if _beg is not None and isinstance(e, _beg):
                logger.error(f"에이전트 비동기 실행 실패(ExceptionGroup/TaskGroup): {e}")
                return self._error_result(f"에이전트 실행 실패: {e}")
            if isinstance(e, Exception):
                logger.error(f"MCP 연결/실행 실패: {e}")
                return self._error_result(f"MCP 도구 로드 실패: {e}")
            raise
    
    async def _run_loop(
        self,
        company: str,
        year: int,
        company_id: Optional[str],
        llm: Any,
        tools: List[BaseTool],
    ) -> Dict[str, Any]:
        """에이전트 메인 루프 (bytes 모드)"""
        system_prompt = self.build_system_prompt(company, year)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"{company}의 {year}년 지속가능경영보고서 PDF를 찾아서 다운로드해 주세요."},
        ]
        
        tool_map = {t.name: t for t in tools}
        result = {"success": False, "message": "", "pdf_bytes": None, "company": company, "year": year, "company_id": company_id}
        
        for i in range(self.max_iterations):
            logger.info(f"[에이전트 반복 {i+1}/{self.max_iterations}]")
            
            # LLM 호출
            try:
                response = await llm.ainvoke(messages)
            except Exception as e:
                logger.error(f"LLM 호출 오류: {e}")
                result["message"] = f"LLM 오류: {e}"
                break
            
            messages.append(response)
            
            # Tool 호출이 없으면 종료
            if not response.tool_calls:
                result["message"] = response.content or ""
                break
            
            # Tool 실행 (한 번에 하나만)
            skipped_msg = '{"skipped": true, "message": "한 번에 하나의 도구만 실행됩니다."}'
            
            for idx, tc in enumerate(response.tool_calls):
                name, args, tc_id = tc["name"], tc["args"], tc["id"]
                
                if idx > 0:
                    messages.append(ToolMessage(content=skipped_msg, tool_call_id=tc_id))
                    continue
                
                # Args 파싱
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {}
                if not isinstance(args, dict):
                    args = {}
                
                # Tool 실행
                if name not in tool_map:
                    tool_result = {"error": f"알 수 없는 도구: {name}"}
                else:
                    try:
                        out = await tool_map[name].ainvoke(args)
                        tool_result = out if isinstance(out, dict) else {"result": str(out)}
                    except Exception as e:
                        # loguru는 {} 스타일 (표준 logging의 %s는 치환되지 않음)
                        logger.exception(
                            "도구 실행 오류: tool={} args_keys={} err={}",
                            name,
                            list(args.keys()) if isinstance(args, dict) else type(args).__name__,
                            e,
                        )
                        tool_result = {"error": str(e)}
                
                # 검색 결과 후처리
                if name == "tavily_search":
                    tool_result, tool_content = self._process_search_result(
                        tool_result, company, tool_map
                    )
                else:
                    tool_content = str(tool_result)
                
                # bytes 다운로드 성공 시 저장
                if name == "download_pdf_bytes" and isinstance(tool_result, dict):
                    success = self._process_bytes_download_result(tool_result, result)
                    if success:
                        messages.append(ToolMessage(content=tool_content, tool_call_id=tc_id))
                        break
                
                messages.append(ToolMessage(content=tool_content, tool_call_id=tc_id))
            
            if result["success"]:
                break
        else:
            if not result["message"]:
                result["message"] = "최대 반복 횟수 초과"
        
        return result
    
    def _process_search_result(
        self,
        tool_result: dict,
        company: str,
        tool_map: Dict[str, BaseTool]
    ) -> tuple[dict, str]:
        """검색 결과 후처리 (도메인 필터링, URL 정렬, PDF 링크 추출)"""
        # 도메인 필터링
        effective_domain = self.tool_utils.company_to_domain_filter(company)
        if isinstance(tool_result, dict) and effective_domain:
            tool_result = self.tool_utils.filter_search_results_by_domain(tool_result, effective_domain)
        
        # URL 추출 및 정렬
        urls, raw_content = self.tool_utils.extract_search_urls(tool_result)
        if not urls:
            return tool_result, raw_content
        
        urls = self.tool_utils.reorder_urls_sustainability_first(urls)
        urls_to_show = urls[:10]

        # URL 목록 로그
        logger.info(f"검색 결과 URL {len(urls_to_show)}개 (최대 10개):")
        for i, u in enumerate(urls_to_show, 1):
            logger.info(f"  [{i}] {u}")

        # 1번 URL에서 PDF 링크 추출 (동기 처리는 비동기로 변환 필요)
        content = f"검색 결과:\n" + "\n".join(f"{i+1}. {u}" for i, u in enumerate(urls_to_show))
        content += f"\n\n→ 첫 번째 URL을 확인하고 PDF를 다운로드하세요.\n\n--- 원본 ---\n{raw_content}"
        
        return tool_result, content
    
    def _process_bytes_download_result(
        self,
        tool_result: dict,
        result: dict,
    ) -> bool:
        """bytes 다운로드 결과 처리"""
        dl_data = tool_result
        
        # JSON 문자열 파싱
        if "result" in tool_result and isinstance(tool_result["result"], str):
            try:
                dl_data = json.loads(tool_result["result"])
            except Exception:
                dl_data = tool_result
        
        # pdf_bytes_b64가 있을 때만 성공
        if dl_data.get("success") and dl_data.get("pdf_bytes_b64"):
            try:
                pdf_bytes = base64.b64decode(dl_data["pdf_bytes_b64"])
            except Exception as e:
                logger.error(f"base64 디코딩 실패: {e}")
                return False
            
            logger.info(f"PDF bytes 수신: {len(pdf_bytes)} bytes")
            
            result["success"] = True
            result["message"] = "PDF 다운로드 완료"
            result["pdf_bytes"] = pdf_bytes
            
            return True
        
        return False
    
    def _error_result(self, message: str) -> Dict[str, Any]:
        """에러 결과 반환"""
        return {"success": False, "message": message, "pdf_bytes": None}
