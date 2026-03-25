"""SRIndexAgent - 인덱스 전용 에이전틱 에이전트.

AGENTIC_INDEX_DESIGN Phase 2. 파싱·검증·보정만 수행하며, 저장은 하지 않습니다 (B안: 오케스트레이터가 저장).
- 입력: pdf_bytes, company, year, report_id
- 역할: get_pdf_metadata / inspect_index_pages / parse_index_with_docling / parse_index_with_llamaparse /
        validate_index_rows / detect_anomalies / correct_anomalous_rows_with_md
- 반환: success, sr_report_index, report_id, errors (호출자가 sr_report_index를 받아 저장 수행)
"""
from __future__ import annotations

import asyncio
import base64
import json
from typing import Any, Dict, List, Optional, TypedDict

from loguru import logger
from backend.core.config.settings import get_settings
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI

from backend.domain.v1.data_integration.spokes.infra.mcp_client import MCPClient
from backend.domain.shared.data_integration.index.review.sr_llm_review import (
    map_page_markdown_to_sr_report_index,
)
from backend.domain.shared.tool.sr_report.index.mapping.sr_index_page_remap import (
    remap_index_page_number_to_original,
    remap_slice_pages_to_original,
)


class IndexAgentState(TypedDict, total=False):
    """에이전트 실행 상태 (AGENTIC_INDEX_DESIGN §5.2)."""
    report_id: str
    pdf_bytes: bytes
    total_pages: Optional[int]
    index_page_numbers: Optional[List[int]]
    page_complexity: Optional[List[dict]]
    docling_rows: Optional[List[dict]]
    llamaparse_md: Optional[Dict[int, str]]
    sr_report_index: Optional[List[dict]]
    merge_observability: Optional[Dict[str, Any]]
    saved_count: int
    message: str
    success: bool
    errors: List[Dict[str, Any]]


class SRIndexAgent:
    """SR 인덱스 저장 전용 에이전트.

    파서 역할 분담(권장):
    - **Docling**: PDF 표 구조·행 단위 추출에 유리 → 병합 시 구조 필드(index_type, dp_id 등) 우선.
    - **LlamaParse + LLM**: page_markdown 기반 인덱스 매핑·누락 보강; 동일 dp_id 다행은 row_sequence로 구분.
    """

    def __init__(
        self,
        openai_api_key: Optional[str] = None,
        model_name: str = "gpt-5-mini",
        max_iterations: int = 50,
    ) -> None:
        api_key = openai_api_key or get_settings().openai_api_key
        if not api_key:
            raise ValueError("OPENAI_API_KEY가 설정되지 않았습니다.")

        self.api_key = api_key
        self.model_name = model_name
        self.max_iterations = max_iterations
        self.mcp_client = MCPClient()
        self.llm = ChatOpenAI(
            model=model_name,
            api_key=api_key,
            temperature=0,
        )

    def build_system_prompt(self) -> str:
        """AGENTIC_INDEX_DESIGN §2.3 기반 + 다중 파서 병합 전략."""
        return """당신은 SR 보고서 인덱스를 파싱하고 sr_report_index 테이블에 저장하는 **전문 에이전트**입니다.
당신은 sr_report_index 테이블 구조, 컬럼 의미, DP→페이지 추출 방법에 대한 전문가 맥락을 갖고 있습니다.

---

## sr_report_index 테이블 전문가 맥락

**테이블 역할**: 기준서별 Index(매핑표)에서 **Data Point ID(DP)별로 해당 페이지 번호 배열**을 저장합니다.

**저장 컬럼 정의**:
| 컬럼 | 타입 | 필수 | 설명 |
|------|------|------|------|
| report_id | UUID | ✓ | historical_sr_reports.id |
| index_type | TEXT | ✓ | 기준서 구분: 'gri' \| 'sasb' \| 'ifrs' \| 'esrs' |
| dp_id | TEXT | ✓ | Data Point ID. 예: GRI-305-1, S2-15-a, ESRS E1-1 |
| page_numbers | INTEGER[] | ✓ | 해당 DP가 나오는 페이지 번호 배열 |
| index_page_number | INTEGER | | 인덱스 표가 있는 원본 페이지 번호 |
| dp_name | TEXT | | 지표명 |
| section_title | TEXT | | 섹션 제목 |
| remarks | TEXT | | 비고 |
| parsing_method | TEXT | | 'docling' \| 'llamaparse' \| 'merged' |
| confidence_score | DECIMAL | | 파싱 신뢰도 (0~100) |

**DP ID 형식**:
- GRI: GRI-2-1, GRI-305-1
- IFRS: S2-6, S2-10, S1-2-d
- SASB: TC-SI-130a.1, TC-SI-220a.4
- ESRS: BP-1, GOV-1, S1-1, E1-1 등

**page_numbers 파싱**:
- 단일: "103" → [103]
- 범위: "7-9" → [7,8,9]
- 혼합: "17, 100-102, 104" → [17,100,101,102,104]

---

## 목표

주어진 PDF의 인덱스 페이지를 파싱·병합·검증·보정하여 **최종 인덱스 배열(sr_report_index)**을 완성합니다.

## 전략 (다중 파서 + 자동 병합)

### 1단계: 정보 수집
- get_pdf_metadata(report_id) → total_pages, index_page_numbers 확인
- (선택) inspect_index_pages(pdf_bytes_b64, index_page_numbers) → 복잡도 파악

### 2단계: 병렬 파싱 (필수)
- **parse_index_with_docling_tool과 parse_index_with_llamaparse_tool을 동시에 호출**
- 시스템이 자동으로 두 결과를 병합합니다:
  * 품질 게이트: Docling은 행·필수 필드 기준. LlamaParse는 **sr_report_index가 비어 있어도 page_markdown이 있으면 통과** 가능
  * LlamaParse가 표 행 없이 마크다운만 주면, 병합 직전 **LLM이 마크다운→sr_report_index 전용 매핑**으로 행을 채움
  * 한쪽만 통과 → 그쪽 사용 (단, LlamaParse 단독은 **행이 채워진 뒤**만 사용; 마크다운만이면 Docling이 있어야 병합 가능)
  * 둘 다 통과 → dp_id 단위 병합 (불일치는 우선순위 규칙으로 해결)
  * 둘 다 실패 → 오류 반환

### 3단계: 병합 결과 확인
- 시스템이 반환하는 병합 메타데이터에는:
  * merge_strategy: "docling_only", "llamaparse_only", "merged", "both_failed"
  * conflicts: 불일치 필드 목록 (자동 해결됨)
  * needs_review: 한쪽만 값 있는 항목 목록 (참고용)
  * quality_report: 각 파서의 품질 평가
- **병합은 코드가 자동 수행하므로, 당신은 결과만 확인하면 됩니다.**
- 불일치(conflicts)가 있어도 이미 해결된 상태이므로, 추가 작업 불필요합니다.

### 4단계: 검증·보정
- validate_index_rows_tool(rows=...) → 스키마 검증
- detect_anomalies_tool(rows=..., total_pages=...) → 이상치 탐지
- (이상치 있을 때만) correct_anomalous_rows_with_md_tool

### 5단계: 완료
검증·보정된 sr_report_index가 준비되면, "인덱스 N건 병합·보정 완료" 메시지 반환

---

## 필수 규칙

1. **병렬 파싱**: get_pdf_metadata 후 **반드시 parse_index_with_docling_tool과 parse_index_with_llamaparse_tool을 같은 턴에 동시 호출**
2. **자동 병합 신뢰**: 시스템이 품질 게이트·병합·불일치 해결을 자동 수행하므로, 당신은 결과를 신뢰하고 다음 단계(검증·보정)로 진행
3. **0건 방지**: 병합 결과가 0건이면 완료로 간주하지 말고 오류 반환
4. **검증 필수**: validate_index_rows_tool, detect_anomalies_tool에 **병합된 sr_report_index 전체** 전달
5. **최대 반복**: {max_iterations}회

---

## LLM 역할 (규칙 기반 최소화)

당신은 다음만 판단합니다:
- **도구 호출 순서** (정보 수집 → 병렬 파싱 → 검증·보정)
- **이상치 보정 여부** (detect_anomalies 결과 기반)
- **완료 조건** (sr_report_index가 1건 이상이고 검증 통과)

다음은 **코드가 자동 수행**하므로 신경 쓰지 마세요:
- 필수 필드 검증 (코드가 처리)
- 파서 결과 병합 (코드가 처리)
- page_numbers 범위 검증 (코드가 처리)
- 불일치 해결 (코드가 우선순위 규칙으로 처리)

당신은 **전략적 판단**에만 집중하고, **세부 규칙은 코드에 위임**하세요.
""".replace("{max_iterations}", str(self.max_iterations))

    def _build_user_prompt(
        self,
        company: str,
        year: int,
        report_id: str,
        pdf_bytes_b64: str,
    ) -> str:
        return f"""아래는 {company}의 {year}년 SR 보고서 PDF bytes(base64)입니다.

company: {company}
year: {year}
report_id: {report_id}
pdf_bytes_b64: {pdf_bytes_b64[:100]}... (총 {len(pdf_bytes_b64)} 문자)

위 PDF에 대해 다음 전략을 따라 인덱스를 파싱·병합·검증·보정하세요:

1) get_pdf_metadata_tool(report_id)로 index_page_numbers, total_pages 확인
2) **parse_index_with_docling_tool과 parse_index_with_llamaparse_tool을 동시에(같은 턴에) 호출**
   - 시스템이 자동으로 두 결과를 병합하고 품질 검증을 수행합니다
   - 병합 결과(merge_strategy, conflicts, needs_review)는 참고용이며, 추가 작업 불필요
3) 병합된 sr_report_index로 validate_index_rows_tool, detect_anomalies_tool 진행
4) 이상치가 있으면 correct_anomalous_rows_with_md_tool로 보정
5) 완료 메시지 반환

**중요**: 병합은 코드가 자동 수행하므로, 당신은 도구 호출 순서만 판단하면 됩니다."""

    def _build_initial_messages(self, system_prompt: str, user_prompt: str) -> List[Any]:
        return [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

    @staticmethod
    def _normalize_tool_call(tc: Any) -> Dict[str, Any]:
        """LangChain/OpenAI tool_calls 항목(dict 또는 객체)을 통일."""
        if isinstance(tc, dict):
            name = str(tc.get("name", "") or "")
            tid = str(tc.get("id", "") or "")
            args = tc.get("args", {})
        else:
            name = str(getattr(tc, "name", "") or "")
            tid = str(getattr(tc, "id", "") or "")
            args = getattr(tc, "args", None)
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except Exception:
                args = {}
        if not isinstance(args, dict):
            args = {}
        return {"name": name, "args": args, "id": tid}

    def _build_result_state(
        self,
        report_id: str,
        success: bool,
        final_message: str,
        sr_report_index: List[Dict[str, Any]],
        errors: List[Dict[str, Any]],
        merge_observability: Optional[Dict[str, Any]] = None,
    ) -> IndexAgentState:
        state: IndexAgentState = {
            "report_id": report_id,
            "success": success,
            "message": final_message,
            "saved_count": 0,
            "sr_report_index": list(sr_report_index),
            "errors": errors,
        }
        if merge_observability is not None:
            state["merge_observability"] = merge_observability
        return state

    async def _prepare_tool_args(
        self,
        *,
        tool_name: str,
        raw_tool_args: dict,
        report_id: str,
        pdf_bytes: bytes,
        pdf_bytes_b64: str,
        last_index_page_numbers: List[int],
        last_sr_report_index: List[Dict[str, Any]],
        last_total_pages: Optional[int],
        last_detect_anomalies_result: List[Dict[str, Any]],
        last_llamaparse_page_markdown: Dict[int, str],
    ) -> tuple[dict, Optional[List[int]]]:
        """도구별 인자 보정 및 자동 주입."""
        current_call_original_pages: Optional[List[int]] = None
        tool_args = raw_tool_args if isinstance(raw_tool_args, dict) else {}

        if tool_name == "get_pdf_metadata_tool":
            tool_args = {"report_id": tool_args.get("report_id") or report_id}
            return tool_args, current_call_original_pages

        if tool_name in {
            "inspect_index_pages_tool",
            "parse_index_with_docling_tool",
            "parse_index_with_llamaparse_tool",
        }:
            tool_args = dict(tool_args)
            pages_to_use = (
                tool_args.get("pages")
                or tool_args.get("index_page_numbers")
                or last_index_page_numbers
            )
            if pages_to_use and isinstance(pages_to_use, list) and len(pages_to_use) > 0:
                from backend.domain.shared.tool.parsing.pdf_pages import (
                    extract_pages_to_pdf_from_bytes,
                )
                extracted_bytes = await asyncio.to_thread(
                    extract_pages_to_pdf_from_bytes, pdf_bytes, pages_to_use
                )
                if extracted_bytes:
                    tool_args["pdf_bytes_b64"] = base64.b64encode(extracted_bytes).decode("utf-8")
                    small_pages = list(range(1, len(pages_to_use) + 1))
                    # MCP 시그니처: inspect=index_page_numbers / 파싱=pages 만 허용 (둘 다 넣으면 FastMCP 검증 실패)
                    if tool_name == "inspect_index_pages_tool":
                        tool_args["index_page_numbers"] = small_pages
                    else:
                        tool_args["pages"] = small_pages
                    current_call_original_pages = list(pages_to_use)
                    logger.info(
                        "[SRIndexAgent] 인덱스 페이지만 추출해 전달: 원본 페이지 {} -> 소 PDF pages {}",
                        pages_to_use,
                        small_pages,
                    )
                else:
                    tool_args["pdf_bytes_b64"] = pdf_bytes_b64
            else:
                tool_args["pdf_bytes_b64"] = pdf_bytes_b64
            # 전체 PDF 경로에서 LLM이 pages를 안 넘긴 경우
            if tool_name in (
                "parse_index_with_docling_tool",
                "parse_index_with_llamaparse_tool",
            ) and not tool_args.get("pages") and last_index_page_numbers:
                tool_args["pages"] = list(last_index_page_numbers)
            if tool_name == "inspect_index_pages_tool" and not tool_args.get(
                "index_page_numbers"
            ) and last_index_page_numbers:
                tool_args["index_page_numbers"] = list(last_index_page_numbers)

        # report_id: Docling·보정 도구만 (LlamaParse MCP 시그니처에는 report_id 없음)
        if tool_name in ("parse_index_with_docling_tool", "correct_anomalous_rows_with_md_tool"):
            tool_args.setdefault("report_id", report_id)

        tool_args = dict(tool_args)
        if tool_name == "validate_index_rows_tool" and not tool_args.get("rows") and last_sr_report_index:
            tool_args["rows"] = last_sr_report_index
            logger.info("[SRIndexAgent] rows 자동 주입 (직전 sr_report_index {}건)", len(last_sr_report_index))
        if tool_name == "detect_anomalies_tool":
            if not tool_args.get("rows") and last_sr_report_index:
                tool_args["rows"] = last_sr_report_index
                logger.info("[SRIndexAgent] detect_anomalies rows 자동 주입")
            if last_total_pages is not None and "total_pages" not in tool_args:
                tool_args["total_pages"] = last_total_pages
                logger.info("[SRIndexAgent] total_pages 자동 주입: {}", last_total_pages)
        if tool_name == "correct_anomalous_rows_with_md_tool":
            if not tool_args.get("anomalous_items") and last_detect_anomalies_result:
                tool_args["anomalous_items"] = last_detect_anomalies_result
                logger.info("[SRIndexAgent] correct_anomalous_rows_with_md anomalous_items 자동 주입 ({}건)", len(last_detect_anomalies_result))
            pm_raw = tool_args.get("page_markdown")
            # LLM이 dict 대신 마크다운 문자열만 넘기는 경우 → {페이지키: md} 로 보정 (Pydantic 검증 통과)
            if isinstance(pm_raw, str) and pm_raw.strip():
                items_for_key = tool_args.get("anomalous_items") or last_detect_anomalies_result
                page_key = 1
                if items_for_key and isinstance(items_for_key[0], dict):
                    ipn = items_for_key[0].get("index_page_number")
                    if isinstance(ipn, int) and ipn >= 1:
                        page_key = ipn
                tool_args["page_markdown"] = {page_key: pm_raw}
                logger.info(
                    "[SRIndexAgent] page_markdown str→dict 보정 (키={}, len={})",
                    page_key,
                    len(pm_raw),
                )
            elif not tool_args.get("page_markdown") and last_llamaparse_page_markdown:
                tool_args["page_markdown"] = last_llamaparse_page_markdown
                logger.info("[SRIndexAgent] correct_anomalous_rows_with_md page_markdown 자동 주입 ({}페이지)", len(last_llamaparse_page_markdown))
            elif tool_args.get("page_markdown") is not None and not isinstance(tool_args["page_markdown"], dict):
                tool_args["page_markdown"] = dict(last_llamaparse_page_markdown) if last_llamaparse_page_markdown else {}
                logger.warning(
                    "[SRIndexAgent] page_markdown 타입 비정상 → last_llamaparse_page_markdown/빈 dict 로 대체",
                )

        # sr_index_tools_server.py FastMCP 시그니처와 불일치 키 제거 (Unexpected keyword 방지)
        _MCP_SR_INDEX_ALLOWED: dict[str, frozenset[str]] = {
            "inspect_index_pages_tool": frozenset({"pdf_bytes_b64", "index_page_numbers"}),
            "parse_index_with_docling_tool": frozenset({"pdf_bytes_b64", "report_id", "pages"}),
            "parse_index_with_llamaparse_tool": frozenset({"pdf_bytes_b64", "pages"}),
            "validate_index_rows_tool": frozenset({"rows"}),
            "detect_anomalies_tool": frozenset({"rows", "total_pages"}),
            "correct_anomalous_rows_with_md_tool": frozenset(
                {"anomalous_items", "page_markdown", "report_id"}
            ),
        }
        _allowed = _MCP_SR_INDEX_ALLOWED.get(tool_name)
        if _allowed is not None:
            tool_args = {k: v for k, v in tool_args.items() if k in _allowed}

        return tool_args, current_call_original_pages

    async def _invoke_tool(
        self,
        *,
        tool_name: str,
        tool_args: dict,
        tools: List[Any],
        report_id: str,
        errors: List[Dict[str, Any]],
    ) -> tuple[Any, Optional[int], Optional[List[int]], Optional[List[Dict[str, Any]]]]:
        """도구 실행 및 공통 후처리."""
        updated_total_pages: Optional[int] = None
        updated_index_page_numbers: Optional[List[int]] = None
        detected_anomalies: Optional[List[Dict[str, Any]]] = None

        if tool_name == "get_pdf_metadata_tool":
            try:
                from backend.domain.shared.tool.sr_report.index.sr_index_agent_tools import (
                    get_pdf_metadata,
                )
                logger.info(f"[SRIndexAgent] 도구 실행 시작: {tool_name} (in-process)")
                meta = await asyncio.to_thread(
                    get_pdf_metadata,
                    tool_args.get("report_id") or report_id,
                )
                tool_result = meta if isinstance(meta, dict) else {"error": str(meta)}
                if isinstance(tool_result, dict) and "error" not in tool_result:
                    logger.info(
                        "[SRIndexAgent] [DEBUG] get_pdf_metadata 반환: total_pages={}, index_page_numbers len={}",
                        tool_result.get("total_pages"), len(tool_result.get("index_page_numbers") or []),
                    )
                    if "total_pages" in tool_result:
                        updated_total_pages = tool_result["total_pages"]
                    if "index_page_numbers" in tool_result:
                        updated_index_page_numbers = list(tool_result.get("index_page_numbers") or [])
                logger.info("[SRIndexAgent] 도구 실행 완료: {}", tool_name)
            except Exception as e:
                logger.error(f"[SRIndexAgent] 도구 실행 오류: {e}")
                tool_result = {"error": str(e)}
                errors.append({"tool": tool_name, "error": str(e)})
            return tool_result, updated_total_pages, updated_index_page_numbers, detected_anomalies

        tool_fn = next((t for t in tools if t.name == tool_name), None)
        if tool_fn is None:
            return {"error": f"알 수 없는 도구: {tool_name}"}, None, None, None

        try:
            logger.info("[SRIndexAgent] 도구 실행 시작: {}", tool_name)
            out = await tool_fn.ainvoke(tool_args)
            if isinstance(out, str):
                try:
                    tool_result = json.loads(out)
                except Exception:
                    tool_result = {"result": out}
            else:
                tool_result = out if isinstance(out, (dict, list)) else {"result": str(out)}

            if isinstance(tool_result, dict):
                keys = list(tool_result.keys())
                if tool_name == "parse_index_with_docling_tool":
                    idx_count = len(tool_result.get("sr_report_index") or [])
                    table_count = tool_result.get("table_count", "?")
                    docling_failed = tool_result.get("docling_failed", False)
                    err = tool_result.get("error", "")
                    logger.info(
                        "[SRIndexAgent] [DEBUG] parse_index_with_docling 반환: sr_report_index={}건, table_count={}, docling_failed={}, error={}",
                        idx_count, table_count, docling_failed, err or "(없음)",
                    )
                elif tool_name == "parse_index_with_llamaparse_tool":
                    pm = tool_result.get("page_markdown") or {}
                    logger.info("[SRIndexAgent] [DEBUG] parse_index_with_llamaparse 반환: page_markdown {}페이지", len(pm))
                else:
                    logger.info("[SRIndexAgent] [DEBUG] {} 반환 키: {}", tool_name, keys)
            elif isinstance(tool_result, list):
                logger.info("[SRIndexAgent] [DEBUG] {} 반환: list len={}", tool_name, len(tool_result))
                if tool_name == "detect_anomalies_tool":
                    detected_anomalies = tool_result
            logger.info("[SRIndexAgent] 도구 실행 완료: {}", tool_name)
            return tool_result, None, None, detected_anomalies
        except Exception as e:
            logger.error(f"[SRIndexAgent] 도구 실행 오류: {e}")
            tool_result = {"error": str(e)}
            errors.append({"tool": tool_name, "error": str(e)})
            return tool_result, None, None, None

    async def _ensure_llamaparse_rows_from_markdown(
        self,
        llamaparse_result: Dict[str, Any],
        *,
        report_id: str,
        last_total_pages: Optional[int],
        last_index_page_numbers: List[int],
    ) -> Dict[str, Any]:
        """
        LlamaParse가 sr_report_index 없이 page_markdown만 줄 때, LLM으로 행 리스트를 채웁니다.
        이미 행이 있으면 그대로 둡니다.
        """
        sr = llamaparse_result.get("sr_report_index") or []
        if len(sr) > 0:
            return llamaparse_result
        pm = llamaparse_result.get("page_markdown") or {}
        if not isinstance(pm, dict) or not any(
            str(v).strip() for v in pm.values() if v is not None
        ):
            return llamaparse_result
        logger.info(
            "[SRIndexAgent] LlamaParse 마크다운→sr_report_index LLM 매핑 시작 (report_id={})",
            report_id,
        )
        rows = await map_page_markdown_to_sr_report_index(
            pm,
            report_id=report_id,
            total_pages=last_total_pages,
            index_page_numbers=last_index_page_numbers or None,
        )
        out = dict(llamaparse_result)
        out["sr_report_index"] = rows
        out["_mapped_from_page_markdown"] = True
        logger.info(
            "[SRIndexAgent] LlamaParse LLM 매핑 완료: {}건",
            len(rows),
        )
        return out

    async def _apply_best_parsing_result(
        self,
        *,
        parsing_results: List[Dict[str, Any]],
        last_sr_report_index: List[Dict[str, Any]],
        last_llamaparse_page_markdown: Dict[int, str],
        last_total_pages: Optional[int],
        report_id: str,
        last_index_page_numbers: List[int],
    ) -> Dict[str, Any]:
        """
        파싱 결과 병합 (다중 파서 + 품질 게이트).

        Returns:
            병합 메타 정보 (merge_strategy, conflicts, needs_review, quality_report)
        """
        logger.info("[SRIndexAgent] 파싱 결과 병합 시작: {}개 결과", len(parsing_results))

        docling_result = None
        llamaparse_result = None
        original_pages_map = {}

        for pr in parsing_results:
            tool_name = pr["tool_name"]
            tool_result = pr["tool_result"]
            current_call_original_pages = pr["current_call_original_pages"]

            if tool_name == "parse_index_with_docling_tool":
                docling_result = tool_result
                original_pages_map["docling"] = current_call_original_pages
            elif tool_name == "parse_index_with_llamaparse_tool":
                llamaparse_result = tool_result
                original_pages_map["llamaparse"] = current_call_original_pages

        if not docling_result and not llamaparse_result:
            logger.warning("[SRIndexAgent] 파싱 결과 없음")
            last_sr_report_index[:] = []
            return {"merge_strategy": "no_results", "error": "파싱 결과 없음"}

        if not docling_result:
            docling_result = {"sr_report_index": [], "error": "docling 미호출"}
        if not llamaparse_result:
            llamaparse_result = {"sr_report_index": [], "error": "llamaparse 미호출"}

        llamaparse_result = await self._ensure_llamaparse_rows_from_markdown(
            llamaparse_result,
            report_id=report_id,
            last_total_pages=last_total_pages,
            last_index_page_numbers=last_index_page_numbers,
        )

        from backend.domain.shared.tool.sr_report.index.multi_parser_merger import (
            merge_parser_results,
        )

        merge_result = merge_parser_results(
            docling_result,
            llamaparse_result,
            total_pages=last_total_pages,
        )

        obs = merge_result.get("observability") or {}
        ov = obs.get("overall") or {}
        logger.info(
            "[SRIndexAgent] 병합 완료: strategy={}, total={}건, conflicts={}건, review={}건, "
            "weighted_agreement={}",
            merge_result.get("merge_strategy"),
            len(merge_result.get("sr_report_index", [])),
            len(merge_result.get("conflicts", [])),
            len(merge_result.get("needs_review", [])),
            f"{ov.get('weighted_agreement_rate'):.4f}"
            if ov.get("weighted_agreement_rate") is not None
            else "n/a",
        )

        merged_items = merge_result.get("sr_report_index", [])
        last_sr_report_index[:] = merged_items

        chosen_pages = (
            original_pages_map.get("docling")
            or original_pages_map.get("llamaparse")
        )
        if chosen_pages and merged_items:
            for item in merged_items:
                pns = item.get("page_numbers")
                if isinstance(pns, list) and pns:
                    item["page_numbers"] = remap_slice_pages_to_original(
                        pns,
                        chosen_pages,
                        total_pages=last_total_pages,
                    )
                ipn = item.get("index_page_number")
                if ipn is not None:
                    item["index_page_number"] = remap_index_page_number_to_original(
                        ipn,
                        chosen_pages,
                        total_pages=last_total_pages,
                    )

        if llamaparse_result and "page_markdown" in llamaparse_result:
            pm = llamaparse_result.get("page_markdown") or {}
            last_llamaparse_page_markdown.clear()
            llama_pages = original_pages_map.get("llamaparse")
            for k, v in pm.items():
                try:
                    idx = int(k)
                    if llama_pages and 1 <= idx <= len(llama_pages):
                        last_llamaparse_page_markdown[llama_pages[idx - 1]] = str(v) if v is not None else ""
                    else:
                        last_llamaparse_page_markdown[idx] = str(v) if v is not None else ""
                except (TypeError, ValueError):
                    pass

        return {
            "merge_strategy": merge_result.get("merge_strategy"),
            "conflicts": merge_result.get("conflicts", []),
            "needs_review": merge_result.get("needs_review", []),
            "quality_report": merge_result.get("quality_report", {}),
            "observability": merge_result.get("observability"),
        }

    async def execute(
        self,
        pdf_bytes: bytes,
        company: str,
        year: int,
        report_id: str,
    ) -> IndexAgentState:
        """에이전트 실행: 인덱스 파싱·저장. MCP(sr_index_tools)로 툴 로드 후 ainvoke 호출."""

        pdf_bytes_b64 = base64.b64encode(pdf_bytes).decode("utf-8")
        system_prompt = self.build_system_prompt()
        user_prompt = self._build_user_prompt(company, year, report_id, pdf_bytes_b64)
        messages = self._build_initial_messages(system_prompt, user_prompt)

        saved_count = 0
        saved_indices: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []
        success = False
        final_message = ""
        last_sr_report_index: List[Dict[str, Any]] = []
        last_total_pages: Optional[int] = None
        last_index_page_numbers: List[int] = []
        last_detect_anomalies_result: List[Dict[str, Any]] = []
        last_llamaparse_page_markdown: Dict[int, str] = {}
        merge_metadata: Dict[str, Any] = {}
        last_merge_observability: Optional[Dict[str, Any]] = None
        tools: List[Any] = []
        llm_with_tools: Any = None

        async with self.mcp_client.tool_runtime("sr_index_tools") as tools:
            if not tools:
                return {
                    "report_id": report_id,
                    "success": False,
                    "message": "인덱스 도구를 로드할 수 없습니다.",
                    "saved_count": 0,
                    "sr_report_index": [],
                    "errors": [{"error": "load_tools 실패"}],
                }
            llm_with_tools = self.llm.bind_tools(tools)

            for i in range(self.max_iterations):
                logger.info("[SRIndexAgent] 반복 {}/{}", i + 1, self.max_iterations)

                try:
                    response = await llm_with_tools.ainvoke(messages)
                except Exception as e:
                    logger.error("[SRIndexAgent] LLM 호출 오류: {}", e)
                    final_message = f"LLM 오류: {e}"
                    break

                messages.append(response)
                tool_calls = getattr(response, "tool_calls", None) or []
                raw_content = getattr(response, "content", None) or ""
                preview = (raw_content[:400] + "…") if len(raw_content) > 400 else raw_content
                tool_names: List[str] = []
                for tc in tool_calls:
                    if isinstance(tc, dict):
                        tool_names.append(str(tc.get("name", "")))
                    else:
                        tool_names.append(str(getattr(tc, "name", "") or ""))
                logger.info(
                    "[SRIndexAgent] LLM 응답: tool_call 수={}, 순서={}, content_len={}",
                    len(tool_calls),
                    tool_names,
                    len(raw_content),
                )
                if preview:
                    logger.debug("[SRIndexAgent] LLM 텍스트(일부): {}", preview)

                if not tool_calls:
                    if len(last_sr_report_index) == 0:
                        success = False
                        final_message = (
                            "sr_report_index가 0건이라 완료할 수 없습니다. "
                            "다른 파싱 도구(parse_index_with_llamaparse_tool)로 재시도하세요."
                        )
                    else:
                        final_message = raw_content or "인덱스 파싱·저장 완료"
                        success = True
                    break

                is_parsing_phase = any(
                    self._normalize_tool_call(tc)["name"]
                    in {"parse_index_with_docling_tool", "parse_index_with_llamaparse_tool"}
                    for tc in tool_calls
                )
                parsing_results: List[Dict[str, Any]] = []

                for idx, tc in enumerate(tool_calls):
                    if not is_parsing_phase and idx > 0:
                        continue

                    ntc = self._normalize_tool_call(tc)
                    tool_name = ntc["name"]
                    tool_args, current_call_original_pages = await self._prepare_tool_args(
                        tool_name=tool_name,
                        raw_tool_args=ntc["args"],
                        report_id=report_id,
                        pdf_bytes=pdf_bytes,
                        pdf_bytes_b64=pdf_bytes_b64,
                        last_index_page_numbers=last_index_page_numbers,
                        last_sr_report_index=last_sr_report_index,
                        last_total_pages=last_total_pages,
                        last_detect_anomalies_result=last_detect_anomalies_result,
                        last_llamaparse_page_markdown=last_llamaparse_page_markdown,
                    )
                    logger.info(f"[SRIndexAgent] 도구 호출: {tool_name}({list(tool_args.keys())})")

                    tool_result, updated_total_pages, updated_index_page_numbers, detected_items = await self._invoke_tool(
                        tool_name=tool_name,
                        tool_args=tool_args,
                        tools=tools,
                        report_id=report_id,
                        errors=errors,
                    )
                    if updated_total_pages is not None:
                        last_total_pages = updated_total_pages
                    if updated_index_page_numbers is not None:
                        last_index_page_numbers = updated_index_page_numbers
                    if detected_items is not None:
                        last_detect_anomalies_result[:] = detected_items

                    if tool_name in {"parse_index_with_docling_tool", "parse_index_with_llamaparse_tool"}:
                        parsing_results.append({
                            "tool_name": tool_name,
                            "tool_result": tool_result,
                            "current_call_original_pages": current_call_original_pages,
                        })

                    messages.append(
                        ToolMessage(
                            content=json.dumps(tool_result, ensure_ascii=False),
                            tool_call_id=ntc["id"],
                        )
                    )

                if is_parsing_phase and parsing_results:
                    merge_metadata = await self._apply_best_parsing_result(
                        parsing_results=parsing_results,
                        last_sr_report_index=last_sr_report_index,
                        last_llamaparse_page_markdown=last_llamaparse_page_markdown,
                        last_total_pages=last_total_pages,
                        report_id=report_id,
                        last_index_page_numbers=last_index_page_numbers,
                    )
                    last_merge_observability = merge_metadata.get("observability")
                    mo = last_merge_observability or {}
                    logger.info(
                        "[SRIndexAgent] 병합 메타: strategy={}, conflicts={}, review={}, "
                        "obs_needs_review={}, obs_conflict_dp={}, obs_w_agree={}",
                        merge_metadata.get("merge_strategy"),
                        len(merge_metadata.get("conflicts", [])),
                        len(merge_metadata.get("needs_review", [])),
                        mo.get("needs_review_count"),
                        mo.get("conflict_dp_count"),
                        (mo.get("overall") or {}).get("weighted_agreement_rate"),
                    )
                else:
                    logger.info(
                        "[SRIndexAgent] 병합 스킵: 이번 턴에 docling/llamaparse 파싱 결과 없음. "
                        "누적 sr_report_index={}건 (이전 턴까지 유지) — 다음 반복에서 에이전트 LLM이 도구 재선택",
                        len(last_sr_report_index),
                    )

                logger.info(
                    "[SRIndexAgent] 턴 종료: sr_report_index={}건, 다음 반복으로 계속 (max={})",
                    len(last_sr_report_index),
                    self.max_iterations,
                )
                continue

            # for 루프 종료: LLM이 tool_calls 없이 끝내지 않고 반복만 소진한 경우
            if final_message == "":
                if len(last_sr_report_index) == 0:
                    success = False
                    final_message = (
                        f"sr_report_index가 0건입니다. 최대 반복({self.max_iterations}) 내에 "
                        "파싱·검증을 완료하지 못했습니다."
                    )
                else:
                    success = True
                    final_message = (
                        f"최대 반복({self.max_iterations}) 도달. "
                        f"인덱스 {len(last_sr_report_index)}건까지 진행됨."
                    )

            logger.info(
                "[SRIndexAgent] 에이전트 종료: success={}, last_sr_report_index={}건, errors={}건, message={}",
                success,
                len(last_sr_report_index),
                len(errors),
                (final_message[:300] + "…") if len(final_message) > 300 else final_message,
            )
            # B안: 저장은 오케스트레이터가 수행. 에이전트는 파싱·보정 결과만 반환.
            return self._build_result_state(
                report_id=report_id,
                success=success,
                final_message=final_message,
                sr_report_index=last_sr_report_index,
                errors=errors,
                merge_observability=last_merge_observability,
            )

