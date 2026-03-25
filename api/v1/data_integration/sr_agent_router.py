"""SR 보고서 검색·다운로드 에이전트 API 라우터.

HTTP 레이어: 라우트·쿼리·응답만 정의. 비즈니스 로직은 Orchestrator에 직접 위임합니다.
"""
import asyncio
import base64
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, Field
from loguru import logger

from backend.core.config.settings import get_settings
from backend.domain.v1.data_integration.hub.orchestrator.sr_orchestrator import SROrchestrator
from backend.domain.shared.tool.parsing.pdf_metadata import parse_sr_report_metadata
from backend.domain.shared.tool.sr_report_tools import parse_sr_report_index


sr_agent_router = APIRouter(prefix="/sr-agent", tags=["SR Agent"])


class ParsingResultResponse(BaseModel):
    """4개 테이블 파싱 결과"""
    historical_sr_reports: Optional[dict] = None
    sr_report_index: List[dict] = []
    sr_report_body: List[dict] = []
    sr_report_images: List[dict] = []
    error: Optional[str] = None


class ExtractParsingResultResponse(BaseModel):
    """extract 전용: historical_sr_reports, sr_report_index만 반환"""
    historical_sr_reports: Optional[dict] = None
    sr_report_index: List[dict] = []
    error: Optional[str] = None


class SRAgentDownloadResponse(BaseModel):
    """기존 다운로드 응답 (파일 저장 모드, 레거시 유지)"""
    success: bool
    path: Optional[str] = None
    message: str
    parsing_result: Optional[dict] = None


class SRAgentExtractResponse(BaseModel):
    """extract 응답: success, message, parsing_result(historical_sr_reports, sr_report_index만)"""
    success: bool
    message: str
    parsing_result: Optional[ExtractParsingResultResponse] = None


# --- 파싱 전용 요청/응답 모델 ---

class ParseMetadataRequest(BaseModel):
    """메타데이터 파싱 요청 (historical_sr_reports)"""
    pdf_path: str = Field(..., description="PDF 파일 경로")
    company: str = Field(..., description="회사명")
    year: int = Field(..., ge=2015, le=2030, description="연도")
    company_id: Optional[str] = None


class ParseTableRequest(BaseModel):
    """인덱스/본문/이미지 파싱 공통 요청"""
    pdf_path: str = Field(..., description="PDF 파일 경로")
    report_id: str = Field(..., description="historical_sr_reports.id")
    index_page_numbers: Optional[List[int]] = Field(default=None, description="인덱스 페이지 번호 목록 (1-based)")


class ParseImagesRequest(ParseTableRequest):
    """이미지 파싱 요청 (image_output_dir 선택)"""
    image_output_dir: Optional[str] = None
    base_name: Optional[str] = None


class ParseAllRequest(BaseModel):
    """통합 파싱 요청 (메타 + 인덱스 + 본문 + 이미지)"""
    pdf_path: str = Field(..., description="PDF 파일 경로")
    company: str = Field(..., description="회사명")
    year: int = Field(..., ge=2015, le=2030, description="연도")
    company_id: Optional[str] = None
    image_output_dir: Optional[str] = None


def _ensure_pdf_path(pdf_path: str) -> None:
    if not Path(pdf_path).exists():
        raise HTTPException(status_code=400, detail=f"PDF 파일을 찾을 수 없습니다: {pdf_path}")


def _resolve_pdf_bytes_for_body_agent(report_id: str, pdf_bytes_b64: Optional[str]) -> bytes:
    """본문/이미지 에이전트용 PDF bytes: 반드시 요청의 pdf_bytes_b64."""
    if pdf_bytes_b64:
        try:
            return base64.b64decode(pdf_bytes_b64)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"pdf_bytes_b64 디코딩 실패: {e}") from e
    try:
        uuid.UUID(str(report_id))
    except ValueError as e:
        raise HTTPException(status_code=400, detail="report_id가 유효한 UUID가 아닙니다.") from e
    raise HTTPException(
        status_code=400,
        detail="pdf_bytes_b64를 제공하세요. (DB에 PDF 파일 경로는 저장하지 않습니다.)",
    )


@sr_agent_router.get("/download", response_model=SRAgentDownloadResponse, deprecated=True)
async def agent_download_sr_report(
    company: str = Query(..., description="회사명 (예: skhynix, 삼성에스디에스). 영문이면 그대로 도메인 필터로 사용"),
    year: int = Query(..., ge=2015, le=2030, description="연도 (예: 2024)"),
) -> SRAgentDownloadResponse:
    """
    [DEPRECATED] 기존 다운로드 모드 (PDF 파일 저장).
    새로운 /extract 엔드포인트를 사용하세요.

    에이전트가 웹 검색을 통해 해당 기업의 지속가능경영보고서 PDF를 찾아
    data_integration/data/ 에 저장합니다.
    """
    try:
        orchestrator = SROrchestrator()
        result = await orchestrator.execute(company=company, year=year, save_to_db=False)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return SRAgentDownloadResponse(**result)


@sr_agent_router.get("/extract", response_model=SRAgentExtractResponse)
async def agent_extract_sr_report(
    company: str = Query(..., description="회사명 (예: skhynix, 삼성에스디에스)"),
    year: int = Query(..., ge=2015, le=2030, description="연도 (예: 2024)"),
    company_id: Optional[str] = Query(None, description="companies.id (선택)"),
    save_to_db: bool = Query(False, description="True면 DB 저장, False면 파싱 결과만 JSON 반환 (확인용)"),
) -> SRAgentExtractResponse:
    """
    에이전트가 웹 검색을 통해 해당 기업의 지속가능경영보고서 PDF를 찾아
    bytes로 가져온 뒤, 4개 테이블 데이터를 JSON으로 추출합니다.
    save_to_db=False(기본): DB 저장 없이 파싱 결과만 반환 (Postman 확인용).
    save_to_db=True: 파싱 후 DB에 저장하고 report_id 반환.

    Returns:
        - parsing_result: historical_sr_reports, sr_report_index, sr_report_body, sr_report_images (save_to_db=False일 때)
    """
    try:
        orchestrator = SROrchestrator()
        result = await orchestrator.execute(
            company=company, year=year, company_id=company_id, save_to_db=save_to_db
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # extract 전용: historical_sr_reports, sr_report_index만 반환
    parsing = result.get("parsing_result")
    if parsing:
        parsing_response = ExtractParsingResultResponse(
            historical_sr_reports=parsing.get("historical_sr_reports"),
            sr_report_index=parsing.get("sr_report_index", []),
            error=parsing.get("error"),
        )
    else:
        parsing_response = None

    return SRAgentExtractResponse(
        success=result.get("success", False),
        message=result.get("message", ""),
        parsing_result=parsing_response,
    )


# --- 테이블별 파싱 엔드포인트 ---

@sr_agent_router.post("/parse/metadata")
async def parse_metadata(req: ParseMetadataRequest) -> Dict[str, Any]:
    """
    PDF에서 메타데이터만 추출하여 historical_sr_reports 1건 분량을 반환합니다.
    """
    _ensure_pdf_path(req.pdf_path)
    result = await asyncio.to_thread(
        parse_sr_report_metadata, req.pdf_path, req.company, req.year, req.company_id
    )
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@sr_agent_router.post("/parse/index")
async def parse_index(req: ParseTableRequest) -> Dict[str, Any]:
    """
    PDF 인덱스 페이지에서 DP→페이지 매핑을 추출하여 sr_report_index 행 목록을 반환합니다.
    """
    _ensure_pdf_path(req.pdf_path)
    if not req.index_page_numbers:
        raise HTTPException(status_code=400, detail="index_page_numbers는 필수입니다.")
    result = await asyncio.to_thread(
        parse_sr_report_index,
        req.pdf_path,
        req.report_id,
        req.index_page_numbers,
    )
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@sr_agent_router.post("/parse/body")
async def parse_body(req: ParseTableRequest) -> Dict[str, Any]:
    """
    본문 에이전트(sr_body_agent) 호출 → parsing + 매핑 (§10).
    PDF 경로에서 bytes를 읽어 에이전트에 전달합니다.
    """
    _ensure_pdf_path(req.pdf_path)
    pdf_bytes = Path(req.pdf_path).read_bytes()
    from backend.domain.v1.data_integration.hub.routing.agent_router import AgentRouter
    router = AgentRouter()
    result = await router.route_to(
        agent_name="sr_body_agent",
        pdf_bytes=pdf_bytes,
        report_id=req.report_id,
        index_page_numbers=req.index_page_numbers,
    )
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("message", "본문 에이전트 실패"))
    return {"sr_report_body": result.get("sr_report_body", [])}


@sr_agent_router.post("/parse/images")
async def parse_images(req: ParseImagesRequest) -> Dict[str, Any]:
    """
    이미지 에이전트(sr_images_agent) 호출 → parsing + 매핑 (§10).
    PDF 경로에서 bytes를 읽어 에이전트에 전달합니다.
    """
    _ensure_pdf_path(req.pdf_path)
    pdf_bytes = Path(req.pdf_path).read_bytes()
    from backend.domain.v1.data_integration.hub.routing.agent_router import AgentRouter
    router = AgentRouter()
    result = await router.route_to(
        agent_name="sr_images_agent",
        pdf_bytes=pdf_bytes,
        report_id=req.report_id,
        index_page_numbers=req.index_page_numbers,
        image_output_dir=req.image_output_dir,
        base_name=req.base_name,
    )
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("message", "이미지 에이전트 실패"))
    return {"sr_report_images": result.get("sr_report_images", [])}


@sr_agent_router.post("/parse/all")
async def parse_all(req: ParseAllRequest) -> Dict[str, Any]:
    """
    메타(parsing) + 인덱스(parsing+mapping) + 본문/이미지(에이전트)로 한 번에 반환 (§10).
    """
    _ensure_pdf_path(req.pdf_path)
    pdf_bytes = Path(req.pdf_path).read_bytes()

    # 1) 메타데이터 (parsing.pdf_metadata)
    meta_result = await asyncio.to_thread(
        parse_sr_report_metadata, req.pdf_path, req.company, req.year, req.company_id
    )
    if "error" in meta_result:
        raise HTTPException(status_code=500, detail=meta_result["error"])
    row = meta_result["historical_sr_reports"]
    report_id = row["id"]
    index_page_numbers = row.get("index_page_numbers") or []

    # 2) 인덱스(parsing+mapping) + 본문/이미지(에이전트) 병렬
    from backend.domain.v1.data_integration.hub.routing.agent_router import AgentRouter
    router = AgentRouter()
    index_result, body_result, images_result = await asyncio.gather(
        asyncio.to_thread(
            parse_sr_report_index, req.pdf_path, report_id, index_page_numbers
        ),
        router.route_to(
            agent_name="sr_body_agent",
            pdf_bytes=pdf_bytes,
            report_id=report_id,
            index_page_numbers=index_page_numbers,
        ),
        router.route_to(
            agent_name="sr_images_agent",
            pdf_bytes=pdf_bytes,
            report_id=report_id,
            index_page_numbers=index_page_numbers,
            image_output_dir=req.image_output_dir,
            base_name=None,
        ),
    )

    out: Dict[str, Any] = {
        "historical_sr_reports": row,
        "sr_report_index": index_result.get("sr_report_index", []) if "error" not in index_result else [],
        "sr_report_body": body_result.get("sr_report_body", []) if body_result.get("success") else [],
        "sr_report_images": images_result.get("sr_report_images", []) if images_result.get("success") else [],
    }
    if "error" in index_result:
        out["sr_report_index_error"] = index_result["error"]
    if not body_result.get("success"):
        out["sr_report_body_error"] = body_result.get("message", "본문 에이전트 실패")
    if not images_result.get("success"):
        out["sr_report_images_error"] = images_result.get("message", "이미지 에이전트 실패")
    return out


# --- 저장 전용 엔드포인트 (Extract + Save 분리) ---

class ExtractAndSaveMetadataRequest(BaseModel):
    """메타데이터 추출 및 저장 요청"""
    company: str = Field(..., description="회사명")
    year: int = Field(..., ge=2015, le=2030, description="연도")
    company_id: Optional[str] = None


class ExtractAndSaveMetadataResponse(BaseModel):
    """메타데이터 저장 응답"""
    success: bool
    message: str
    report_id: Optional[str] = None
    historical_sr_reports: Optional[dict] = None


class ExtractAndSaveIndexRequest(BaseModel):
    """인덱스 추출 및 저장 요청"""
    company: str = Field(..., description="회사명")
    year: int = Field(..., ge=2015, le=2030, description="연도")
    report_id: str = Field(..., description="저장된 report_id (메타데이터 저장 후 획득)")


class ExtractAndSaveIndexAgenticRequest(BaseModel):
    """에이전틱 인덱스 저장 요청. sr_agent → 메타 저장(report_id) → sr_index_agent 체인으로 bytes 전달."""
    company: str = Field(..., description="회사명 (sr_agent 검색·다운로드용)")
    year: int = Field(..., ge=2015, le=2030, description="연도 (sr_agent용)")
    company_id: Optional[str] = Field(default=None, description="companies.id (선택)")


class ExtractAndSaveIndexResponse(BaseModel):
    """인덱스 저장 응답"""
    success: bool
    message: str
    saved_count: int = 0
    errors: List[dict] = []
    sr_report_index: Optional[List[dict]] = None


class ExtractAndSaveBodyRequest(BaseModel):
    """본문 추출 및 저장 요청"""
    company: str = Field(..., description="회사명")
    year: int = Field(..., ge=2015, le=2030, description="연도")
    report_id: str = Field(..., description="저장된 report_id")


class ExtractAndSaveBodyAgenticRequest(BaseModel):
    """본문 에이전트(SRBodyAgent) 직접 실행: SR_BODY_PARSING_DESIGN §6.4."""

    report_id: str = Field(..., description="historical_sr_reports.id (UUID)")
    pdf_bytes_b64: Optional[str] = Field(
        default=None,
        description="필수에 가깝게 권장. PDF 바이너리 base64 (DB에 로컬 경로는 저장하지 않음).",
    )


class ExtractAndSaveBodyResponse(BaseModel):
    """본문 저장 응답 (LangGraph `extract-and-save/body` / 직접 `body-agentic` 공통)."""

    success: bool
    message: str
    saved_count: int = 0
    errors: List[dict] = Field(default_factory=list, description="SRBodyAgent 오류 등 (가능하면 채움)")
    report_id: Optional[str] = Field(default=None, description="요청에 사용한 report_id")
    fetch_success: Optional[bool] = Field(
        default=None,
        description="extract-and-save/body만: SRAgent PDF fetch 성공 여부",
    )
    fetch_message: Optional[str] = Field(
        default=None,
        description="extract-and-save/body만: fetch 단계 message(예: PDF 다운로드 완료)",
    )
    body_agent_success: Optional[bool] = Field(
        default=None,
        description="SRBodyAgent가 반환한 success",
    )
    body_agent_message: Optional[str] = Field(
        default=None,
        description="SRBodyAgent가 반환한 message",
    )
    db_sr_report_body_row_count: Optional[int] = Field(
        default=None,
        description="요청 종료 시점 DB sr_report_body 행 수(해당 report_id)",
    )


class ExtractAndSaveImagesRequest(BaseModel):
    """이미지 추출 및 저장 요청"""
    company: str = Field(..., description="회사명")
    year: int = Field(..., ge=2015, le=2030, description="연도")
    report_id: str = Field(..., description="저장된 report_id")
    image_output_dir: Optional[str] = Field(
        default=None,
        description="SR_IMAGE_STORAGE=disk 일 때만(또는 SR_IMAGE_OUTPUT_DIR). 기본 memory는 불필요.",
    )
    success_includes_vlm: bool = Field(
        default=False,
        description=(
            "True면 저장 성공 후 자동 VLM이 실행되어 images_vlm_auto_success=False인 경우 "
            "응답 success도 False (미실행/스킵(None)은 저장 성공만으로 판단)."
        ),
    )


class ExtractAndSaveImagesResponse(BaseModel):
    """이미지 저장 응답 (LangGraph `extract-and-save/images` / `images-agentic` 공통 필드)."""

    success: bool
    message: str
    saved_count: int = 0
    errors: List[dict] = Field(default_factory=list)
    report_id: Optional[str] = Field(default=None, description="요청에 사용한 report_id")
    fetch_success: Optional[bool] = Field(
        default=None,
        description="extract-and-save/images만: SRAgent PDF fetch 성공 여부",
    )
    fetch_message: Optional[str] = Field(default=None, description="fetch 단계 메시지")
    images_agent_success: Optional[bool] = Field(default=None, description="SRImagesAgent success")
    images_agent_message: Optional[str] = Field(default=None, description="SRImagesAgent message")
    db_sr_report_images_row_count: Optional[int] = Field(
        default=None,
        description="요청 종료 시점 DB sr_report_images 행 수(해당 report_id)",
    )
    images_vlm_auto_success: Optional[bool] = Field(
        default=None,
        description="저장 직후 자동 VLM 보강 성공 여부(OPENAI_API_KEY·SR_IMAGE_VLM_AUTO_AFTER_SAVE)",
    )
    images_vlm_auto_message: Optional[str] = Field(default=None, description="자동 VLM 보강 메시지")
    images_vlm_auto_updated: Optional[int] = Field(default=None, description="VLM으로 갱신된 행 수")
    images_vlm_auto_skipped: Optional[int] = Field(default=None, description="바이트 없음 등 스킵 행 수")


class ExtractAndSaveImagesAgenticRequest(BaseModel):
    """이미지 에이전트(SRImagesAgent) 직접 실행: SR_IMAGES_PARSING_DESIGN."""

    report_id: str = Field(..., description="historical_sr_reports.id (UUID)")
    pdf_bytes_b64: Optional[str] = Field(
        default=None,
        description="필수에 가깝게 권장. PDF 바이너리 base64 (DB에 로컬 경로는 저장하지 않음).",
    )
    image_output_dir: Optional[str] = Field(
        default=None,
        description="SR_IMAGE_STORAGE=disk 일 때만 필요(또는 SR_IMAGE_OUTPUT_DIR). memory/s3 기본은 무시 가능.",
    )
    success_includes_vlm: bool = Field(
        default=False,
        description=(
            "True면 자동 VLM이 실행되어 images_vlm_auto_success=False인 경우 응답 success도 False."
        ),
    )


class EnrichImagesVlmRequest(BaseModel):
    """sr_report_images 에 OpenAI VLM(gpt-5-mini 등)으로 image_type·caption·confidence 보강."""

    report_id: str = Field(..., description="historical_sr_reports.id (UUID)")
    skip_if_caption_set: bool = Field(
        default=False,
        description="이미 caption_text가 비어 있지 않으면 해당 행 스킵",
    )


class EnrichImagesVlmResponse(BaseModel):
    success: bool
    message: str
    processed: int = 0
    updated: int = 0
    skipped: int = 0
    errors: List[dict] = Field(default_factory=list)


@sr_agent_router.post("/extract-and-save/metadata", response_model=ExtractAndSaveMetadataResponse)
async def extract_and_save_metadata(req: ExtractAndSaveMetadataRequest) -> ExtractAndSaveMetadataResponse:
    """
    1단계: SR 보고서를 검색하여 다운로드하고, 메타데이터만 파싱하여 DB에 저장합니다.
    LangGraph로 fetch → save_metadata 노드만 실행.
    """
    try:
        from backend.domain.v1.data_integration.models.langgraph import SRWorkflowState
        from backend.domain.v1.data_integration.hub.orchestrator.sr_workflow import get_sr_graph

        initial_state: SRWorkflowState = {
            "company": req.company,
            "year": req.year,
            "company_id": req.company_id,
            "save_to_db": True,
            "only_step": "metadata",
        }
        graph = get_sr_graph()
        final_state = await graph.ainvoke(initial_state)

        success = final_state.get("success", False)
        if not success and not final_state.get("report_id"):
            return ExtractAndSaveMetadataResponse(
                success=False,
                message=final_state.get("message", "메타데이터 저장 실패"),
            )
        return ExtractAndSaveMetadataResponse(
            success=True,
            message="메타데이터 저장 완료",
            report_id=final_state.get("report_id"),
            historical_sr_reports=final_state.get("historical_sr_reports"),
        )
    except Exception as e:
        logger.error(f"[API] 메타데이터 저장 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@sr_agent_router.post("/extract-and-save/index", response_model=ExtractAndSaveIndexResponse)
async def extract_and_save_index(req: ExtractAndSaveIndexRequest) -> ExtractAndSaveIndexResponse:
    """
    2단계: SR 보고서의 인덱스를 파싱하고 배치로 DB에 저장합니다.
    LangGraph로 fetch → save_index 노드만 실행 (report_id는 state로 전달, index_page_numbers는 DB 조회).
    """
    try:
        from backend.domain.v1.data_integration.models.langgraph import SRWorkflowState
        from backend.domain.v1.data_integration.hub.orchestrator.sr_workflow import get_sr_graph

        initial_state: SRWorkflowState = {
            "company": req.company,
            "year": req.year,
            "report_id": req.report_id,
            "save_to_db": True,
            "only_step": "index",
        }
        graph = get_sr_graph()
        final_state = await graph.ainvoke(initial_state)

        saved = final_state.get("index_saved_count", 0)
        return ExtractAndSaveIndexResponse(
            success=final_state.get("success", False),
            message=final_state.get("message") or f"인덱스 {saved}건 저장 완료",
            saved_count=saved,
            errors=[],
        )
    except Exception as e:
        logger.error(f"[API] 인덱스 저장 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@sr_agent_router.post("/extract-and-save/index-agentic", response_model=ExtractAndSaveIndexResponse)
async def extract_and_save_index_agentic(req: ExtractAndSaveIndexAgenticRequest) -> ExtractAndSaveIndexResponse:
    """
    에이전틱 인덱스 저장: hub/orchestrator(LangGraph) 한 번만 경유.
    fetch_and_parse → save_metadata → save_index(sr_index_agent + 저장) → END.
    """
    orchestrator = SROrchestrator()
    result = await orchestrator.execute(
        company=req.company,
        year=req.year,
        company_id=req.company_id,
        save_to_db=True,
        only_step="index",
    )
    return ExtractAndSaveIndexResponse(
        success=result.get("success", False),
        message=result.get("message", ""),
        saved_count=result.get("index_saved_count", 0),
        errors=[],  # 오케스트레이터 반환에 errors 필드 추가 시 여기 매핑 가능
        sr_report_index=result.get("sr_report_index") or [],
    )


@sr_agent_router.post("/extract-and-save/body", response_model=ExtractAndSaveBodyResponse)
async def extract_and_save_body(req: ExtractAndSaveBodyRequest) -> ExtractAndSaveBodyResponse:
    """
    3단계: SR 보고서 본문을 DB(`sr_report_body`)에 저장합니다.

    **SRAgent fetch**: `company`/`year`로 PDF를 다시 검색·다운로드한 뒤, 기존 `report_id`에 본문을 넣습니다.
    `report_id`가 state에 있으면 **메타데이터 INSERT 없이** fetch → `save_body`만 수행합니다
    (`pdf_bytes_b64` 불필요 — 워크플로가 fetch로 PDF를 채움).
    """
    try:
        from backend.domain.v1.data_integration.models.langgraph import SRWorkflowState
        from backend.domain.v1.data_integration.hub.orchestrator.sr_workflow import get_sr_graph

        initial_state: SRWorkflowState = {
            "company": req.company,
            "year": req.year,
            "report_id": req.report_id,
            "save_to_db": True,
            "only_step": "body",
        }
        graph = get_sr_graph()
        final_state = await graph.ainvoke(initial_state)

        saved = int(final_state.get("body_saved_count", 0) or 0)
        fetch_ok = bool(final_state.get("success", False))
        fetch_msg = (final_state.get("message") or "").strip()
        body_ok = final_state.get("body_agent_success")
        body_msg = (final_state.get("body_agent_message") or "").strip()
        raw_errs = final_state.get("body_agent_errors")
        err_list: List[dict] = []
        if isinstance(raw_errs, list):
            err_list = [e for e in raw_errs if isinstance(e, dict)]
        elif raw_errs:
            err_list = [{"detail": str(raw_errs)}]
        db_rows = final_state.get("sr_report_body_db_row_count")

        if fetch_ok and saved > 0:
            summary = (
                f"{fetch_msg} 본문 {saved}건 저장 완료."
                if fetch_msg
                else f"본문 {saved}건 저장 완료."
            )
        elif fetch_ok and saved == 0:
            summary = (
                f"{fetch_msg} 본문 0건 저장."
                if fetch_msg
                else "본문 0건 저장."
            )
            if body_msg:
                summary += f" 에이전트 메시지: {body_msg}"
            if err_list:
                summary += f" (에이전트 오류 {len(err_list)}건)"
        else:
            summary = fetch_msg or "PDF fetch 실패 또는 본문 단계 미실행"

        return ExtractAndSaveBodyResponse(
            success=fetch_ok and saved > 0,
            message=summary,
            saved_count=saved,
            errors=err_list,
            report_id=req.report_id,
            fetch_success=fetch_ok,
            fetch_message=fetch_msg or None,
            body_agent_success=body_ok,
            body_agent_message=body_msg or None,
            db_sr_report_body_row_count=db_rows if isinstance(db_rows, int) else None,
        )
    except Exception as e:
        logger.error(f"[API] 본문 저장 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@sr_agent_router.post("/extract-and-save/body-agentic", response_model=ExtractAndSaveBodyResponse)
async def extract_and_save_body_agentic(req: ExtractAndSaveBodyAgenticRequest) -> ExtractAndSaveBodyResponse:
    """
    SRBodyAgent(결정적 파이프라인: 메타데이터→파싱→매핑→저장)으로 페이지별 본문을 추출해 `sr_report_body`에 저장합니다.
    **SRAgent로 PDF를 다시 받아 저장**하려면 `POST .../extract-and-save/body`(company, year, report_id)를 사용하세요.

    이 엔드포인트는 LangGraph·재검색 없이 `report_id`와 `pdf_bytes_b64`(필수)만 사용합니다.
    """
    try:
        pdf_bytes = _resolve_pdf_bytes_for_body_agent(req.report_id, req.pdf_bytes_b64)
        from backend.domain.v1.data_integration.spokes.agents.sr_body_agent import SRBodyAgent

        agent = SRBodyAgent()
        result = await agent.execute(pdf_bytes=pdf_bytes, report_id=req.report_id)
        errs = result.get("errors")
        err_list: List[dict] = (
            [e for e in errs if isinstance(e, dict)] if isinstance(errs, list) else []
        )
        saved = int(result.get("saved_count", 0) or 0)

        from backend.domain.v1.data_integration.hub.repositories.sr_report_body_repository import (
            count_sr_report_body_rows,
        )

        db_rows = await asyncio.to_thread(count_sr_report_body_rows, req.report_id)

        agent_success = bool(result.get("success"))
        return ExtractAndSaveBodyResponse(
            success=saved > 0,
            message=str(result.get("message", "")),
            saved_count=saved,
            errors=err_list,
            report_id=req.report_id,
            fetch_success=None,
            fetch_message=None,
            body_agent_success=agent_success,
            body_agent_message=str(result.get("message", "")) or None,
            db_sr_report_body_row_count=db_rows,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] body-agentic 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@sr_agent_router.post("/extract-and-save/images", response_model=ExtractAndSaveImagesResponse)
async def extract_and_save_images(req: ExtractAndSaveImagesRequest) -> ExtractAndSaveImagesResponse:
    """
    4단계: SR 보고서의 이미지를 파싱하고 DB에 저장합니다.
    LangGraph로 fetch → save_images 노드만 실행. 저장 성공 후 `OPENAI_API_KEY`가 있으면 자동 VLM 보강.
    `SR_IMAGE_STORAGE=disk`일 때만 이미지 파일 경로가 필요합니다. 기본(memory)은 메타만 DB에 저장합니다.
    """
    try:
        from backend.domain.v1.data_integration.models.langgraph import SRWorkflowState
        from backend.domain.v1.data_integration.hub.orchestrator.sr_workflow import get_sr_graph

        initial_state: SRWorkflowState = {
            "company": req.company,
            "year": req.year,
            "report_id": req.report_id,
            "save_to_db": True,
            "only_step": "images",
            "image_output_dir": req.image_output_dir,
        }
        graph = get_sr_graph()
        final_state = await graph.ainvoke(initial_state)

        saved = int(final_state.get("images_saved_count", 0) or 0)
        fetch_ok = bool(final_state.get("success", False))
        fetch_msg = (final_state.get("message") or "").strip()
        img_ok = final_state.get("images_agent_success")
        img_msg = (final_state.get("images_agent_message") or "").strip()
        raw_errs = final_state.get("images_agent_errors")
        err_list: List[dict] = []
        if isinstance(raw_errs, list):
            err_list = [e for e in raw_errs if isinstance(e, dict)]
        elif raw_errs:
            err_list = [{"detail": str(raw_errs)}]
        db_rows = final_state.get("sr_report_images_db_row_count")
        if isinstance(db_rows, int):
            db_out: Optional[int] = db_rows
        else:
            db_out = None

        if fetch_ok and saved > 0:
            summary = (
                f"{fetch_msg} 이미지 {saved}건 저장 완료."
                if fetch_msg
                else f"이미지 {saved}건 저장 완료."
            )
        elif fetch_ok and saved == 0:
            summary = (
                f"{fetch_msg} 이미지 0건 저장."
                if fetch_msg
                else "이미지 0건 저장."
            )
            if img_msg:
                summary += f" 에이전트: {img_msg}"
            if err_list:
                summary += f" (오류 {len(err_list)}건)"
        else:
            summary = fetch_msg or "PDF fetch 실패 또는 이미지 단계 미실행"

        vlm_msg = (final_state.get("images_vlm_auto_message") or "").strip()
        if vlm_msg:
            summary = f"{summary} VLM: {vlm_msg}"

        save_ok = fetch_ok and saved > 0
        vlm_ok = not req.success_includes_vlm or final_state.get("images_vlm_auto_success") is not False

        return ExtractAndSaveImagesResponse(
            success=save_ok and vlm_ok,
            message=summary,
            saved_count=saved,
            errors=err_list,
            report_id=req.report_id,
            fetch_success=fetch_ok,
            fetch_message=fetch_msg or None,
            images_agent_success=img_ok,
            images_agent_message=img_msg or None,
            db_sr_report_images_row_count=db_out,
            images_vlm_auto_success=final_state.get("images_vlm_auto_success"),
            images_vlm_auto_message=final_state.get("images_vlm_auto_message"),
            images_vlm_auto_updated=final_state.get("images_vlm_auto_updated"),
            images_vlm_auto_skipped=final_state.get("images_vlm_auto_skipped"),
        )
    except Exception as e:
        logger.error(f"[API] 이미지 저장 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@sr_agent_router.post("/extract-and-save/images-agentic", response_model=ExtractAndSaveImagesResponse)
async def extract_and_save_images_agentic(req: ExtractAndSaveImagesAgenticRequest) -> ExtractAndSaveImagesResponse:
    """
    SRImagesAgent(결정적: 메타 조회 → PyMuPDF 추출 → 배치 저장)으로 `sr_report_images`에 저장합니다.
    LangGraph·재검색 없이 `report_id`와 `pdf_bytes_b64`(필수)를 사용합니다. 저장 성공 후 자동 VLM 보강(키 있을 때).
    """
    try:
        pdf_bytes = _resolve_pdf_bytes_for_body_agent(req.report_id, req.pdf_bytes_b64)
        from backend.domain.v1.data_integration.spokes.agents.sr_images_agent import SRImagesAgent
        from backend.domain.v1.data_integration.hub.repositories.sr_report_images_repository import (
            count_sr_report_images_rows,
        )

        agent = SRImagesAgent()
        result = await agent.execute(
            pdf_bytes=pdf_bytes,
            report_id=req.report_id,
            image_output_dir=req.image_output_dir,
        )
        errs = result.get("errors")
        err_list: List[dict] = (
            [e for e in errs if isinstance(e, dict)] if isinstance(errs, list) else []
        )
        saved = int(result.get("saved_count", 0) or 0)
        db_rows = await asyncio.to_thread(count_sr_report_images_rows, req.report_id)
        agent_success = bool(result.get("success"))

        vlm_s: Optional[bool] = None
        vlm_m: Optional[str] = None
        vlm_u: Optional[int] = None
        vlm_sk: Optional[int] = None
        base_msg = str(result.get("message", ""))
        if agent_success and saved > 0:
            from backend.domain.v1.data_integration.spokes.infra.sr_image_vlm_enrichment import (
                maybe_auto_enrich_after_image_save,
            )

            vlm_result = await asyncio.to_thread(maybe_auto_enrich_after_image_save, req.report_id)
            if vlm_result is not None:
                vlm_s = bool(vlm_result.get("success"))
                vlm_m = str(vlm_result.get("message", "")) or None
                vlm_u = int(vlm_result.get("updated", 0) or 0)
                vlm_sk = int(vlm_result.get("skipped", 0) or 0)
                if vlm_m:
                    base_msg = f"{base_msg} VLM: {vlm_m}"

        save_ok = saved > 0
        vlm_ok_row = not req.success_includes_vlm or vlm_s is not False

        return ExtractAndSaveImagesResponse(
            success=save_ok and vlm_ok_row,
            message=base_msg,
            saved_count=saved,
            errors=err_list,
            report_id=req.report_id,
            fetch_success=None,
            fetch_message=None,
            images_agent_success=agent_success,
            images_agent_message=str(result.get("message", "")) or None,
            db_sr_report_images_row_count=db_rows,
            images_vlm_auto_success=vlm_s,
            images_vlm_auto_message=vlm_m,
            images_vlm_auto_updated=vlm_u,
            images_vlm_auto_skipped=vlm_sk,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] images-agentic 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@sr_agent_router.post("/enrich-images-vlm", response_model=EnrichImagesVlmResponse)
async def enrich_images_vlm(req: EnrichImagesVlmRequest) -> EnrichImagesVlmResponse:
    """
    `sr_report_images` 행에 대해 VLM으로 `image_type`, `caption_text`, `caption_confidence` 를 채웁니다.
    이미지 바이트는 `image_blob` 또는 S3(`extracted_data`)에서 로드합니다. [SR_IMAGES_VLM_ENRICHMENT.md]

    모델은 코드 상수 `gpt-5-mini` 고정. `OPENAI_API_KEY` 필요.
    """
    from backend.domain.v1.data_integration.spokes.infra.sr_image_vlm_enrichment import (
        enrich_sr_report_images_vlm,
    )

    if not get_settings().openai_api_key.strip():
        raise HTTPException(status_code=400, detail="OPENAI_API_KEY가 필요합니다.")

    result = await asyncio.to_thread(
        enrich_sr_report_images_vlm,
        req.report_id,
        skip_if_caption_set=req.skip_if_caption_set,
    )
    errs = result.get("errors")
    err_list: List[dict] = [e for e in errs if isinstance(e, dict)] if isinstance(errs, list) else []
    return EnrichImagesVlmResponse(
        success=bool(result.get("success")),
        message=str(result.get("message", "")),
        processed=int(result.get("processed", 0) or 0),
        updated=int(result.get("updated", 0) or 0),
        skipped=int(result.get("skipped", 0) or 0),
        errors=err_list,
    )
