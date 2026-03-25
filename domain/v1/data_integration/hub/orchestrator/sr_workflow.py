"""SR 워크플로우 (LangGraph)

StateGraph: fetch_and_parse → (조건) → save_metadata → save_index → save_body → save_images → END
상태 전달: backend.domain.v1.data_integration.models.langgraph.SRWorkflowState
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any, Dict, List, Literal

from loguru import logger

try:
    from langgraph.graph import StateGraph, END
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    StateGraph = None
    END = None

from ...models.langgraph import SRWorkflowState


def _route_after_fetch(
    state: SRWorkflowState,
) -> Literal["save_metadata", "save_index", "save_body", "save_images", "parse_only", "end"]:
    """fetch_and_parse 이후: save_to_db면 기본은 save_metadata.

    **기존 report_id가 state에 있으면** 메타 INSERT를 건너뛰고 SRAgent가 가져온 pdf_bytes로
    해당 단계만 실행 (extract-and-save/index|body|images API와 동일한 의도).
    """
    if not state.get("success") or not state.get("pdf_bytes"):
        return "end"
    if not state.get("save_to_db"):
        return "parse_only"

    only = state.get("only_step")
    rid = state.get("report_id")

    if only == "index" and rid:
        logger.info("[SRWorkflow] fetch 완료 → 기존 report_id로 save_index (save_metadata 생략)")
        return "save_index"
    if only == "body" and rid:
        logger.info("[SRWorkflow] fetch 완료 → 기존 report_id로 save_body (save_metadata 생략)")
        return "save_body"
    if only == "images" and rid:
        logger.info("[SRWorkflow] fetch 완료 → 기존 report_id로 save_images (save_metadata 생략)")
        return "save_images"

    return "save_metadata"


async def _fetch_and_parse_node(state: SRWorkflowState) -> Dict[str, Any]:
    """노드 1: SRAgent 실행 (MCP 검색·다운로드). 상태에 pdf_bytes 반영."""
    from ..routing.agent_router import AgentRouter

    company = state["company"]
    year = state["year"]
    company_id = state.get("company_id")

    router = AgentRouter()
    result = await router.route_to(
        agent_name="sr_agent",
        company=company,
        year=year,
        company_id=company_id,
    )

    return {
        "success": result.get("success", False),
        "message": result.get("message", ""),
        "pdf_bytes": result.get("pdf_bytes"),
    }


async def _save_metadata_node(state: SRWorkflowState) -> Dict[str, Any]:
    """노드 2: 메타데이터 파싱(parsing) → LLM 검토 → DB 저장."""
    from backend.domain.shared.tool.parsing.pdf_metadata import parse_sr_report_metadata
    from backend.domain.shared.tool.sr_report.save.sr_save_tools import (
        save_historical_sr_report,
    )
    from backend.domain.shared.data_integration.index.review.sr_llm_review import review_sr_metadata_with_llm

    pdf_bytes = state.get("pdf_bytes")
    if not pdf_bytes:
        logger.warning("[SRWorkflow] save_metadata: pdf_bytes 없음")
        return {"message": "pdf_bytes 없음"}

    company = state["company"]
    year = state["year"]
    company_id = state.get("company_id")

    meta_result = await asyncio.to_thread(
        parse_sr_report_metadata, pdf_bytes, company, year, company_id
    )
    if "error" in meta_result:
        logger.error(f"[SRWorkflow] save_metadata 파싱 실패: {meta_result['error']}")
        return {"message": meta_result["error"]}

    meta = meta_result["historical_sr_reports"]
    meta = await review_sr_metadata_with_llm(meta, company, year)

    report_id = await asyncio.to_thread(
        save_historical_sr_report.invoke,
        {
            "company_id": meta.get("company_id"),
            "report_year": meta["report_year"],
            "report_name": meta["report_name"],
            "source": meta["source"],
            "total_pages": meta.get("total_pages", 0),
            "index_page_numbers": meta.get("index_page_numbers", []),
        },
    )
    index_page_numbers = meta.get("index_page_numbers")

    logger.info(f"[SRWorkflow] save_metadata 완료: report_id={report_id}")
    return {
        "report_id": report_id,
        "index_page_numbers": index_page_numbers,
        "historical_sr_reports": meta,
    }


def _load_index_page_numbers_from_db(report_id: str) -> list:
    """report_id로 DB에서 index_page_numbers 조회 (only_step 호출 시 사용)."""
    from backend.domain.v1.ifrs_agent.database.base import get_session
    from backend.domain.v1.data_integration.models.bases import HistoricalSRReport

    session = get_session()
    try:
        report = session.query(HistoricalSRReport).filter(
            HistoricalSRReport.id == uuid.UUID(report_id)
        ).first()
        return (report.index_page_numbers or []) if report else []
    finally:
        session.close()


async def _save_index_node(state: SRWorkflowState) -> Dict[str, Any]:
    """노드 3: sr_index_agent 호출(파싱·검증·보정) → 오케스트레이터가 save_sr_report_index_batch로 저장."""
    from backend.domain.shared.tool.sr_report.save.sr_save_tools import save_sr_report_index_batch
    from ..routing.agent_router import AgentRouter

    pdf_bytes = state.get("pdf_bytes")
    report_id = state.get("report_id")
    company = state.get("company", "")
    year = state.get("year", 0)

    if not pdf_bytes or not report_id:
        logger.warning("[SRWorkflow] save_index: pdf_bytes 또는 report_id 없음")
        return {"index_saved_count": 0}

    router = AgentRouter()
    result = await router.route_to(
        agent_name="sr_index_agent",
        pdf_bytes=pdf_bytes,
        company=company,
        year=year,
        report_id=report_id,
    )

    if not result.get("success"):
        logger.warning(
            "[SRWorkflow] save_index: sr_index_agent 실패: {}",
            result.get("message", "unknown"),
        )
        return {
            "index_saved_count": 0,
            "message": result.get("message", "인덱스 파싱·보정 실패"),
            "sr_report_index": result.get("sr_report_index"),
        }

    sr_report_index = result.get("sr_report_index") or []
    if not sr_report_index:
        logger.info("[SRWorkflow] save_index: sr_report_index 없음, 스킵")
        return {"index_saved_count": 0, "sr_report_index": []}

    save_result = await asyncio.to_thread(
        save_sr_report_index_batch.invoke,
        {"report_id": report_id, "indices": sr_report_index},
    )
    saved = save_result.get("saved_count", 0) if isinstance(save_result, dict) else 0
    logger.info("[SRWorkflow] save_index 완료: {}건", saved)
    return {
        "index_saved_count": saved,
        "sr_report_index": sr_report_index,
    }


async def _save_body_node(state: SRWorkflowState) -> Dict[str, Any]:
    """노드 4: 본문 에이전트(sr_body_agent) 호출 → parsing + 매핑·저장 (§10)."""
    from ..routing.agent_router import AgentRouter

    pdf_bytes = state.get("pdf_bytes")
    report_id = state.get("report_id")
    index_page_numbers = state.get("index_page_numbers")
    if index_page_numbers is None and report_id:
        index_page_numbers = await asyncio.to_thread(
            _load_index_page_numbers_from_db, report_id
        )

    if not pdf_bytes or not report_id:
        logger.warning("[SRWorkflow] save_body: pdf_bytes 또는 report_id 없음")
        return {}

    router = AgentRouter()
    result = await router.route_to(
        agent_name="sr_body_agent",
        pdf_bytes=pdf_bytes,
        report_id=report_id,
        index_page_numbers=index_page_numbers,
    )
    saved = int(result.get("saved_count", 0) or 0)
    agent_ok = bool(result.get("success", False))
    agent_msg = (result.get("message") or "") if isinstance(result.get("message"), str) else str(
        result.get("message") or ""
    )
    raw_errs = result.get("errors")
    if raw_errs is None:
        body_errors: list = []
    elif isinstance(raw_errs, list):
        body_errors = raw_errs
    else:
        body_errors = [{"detail": str(raw_errs)}]

    from ..repositories.sr_report_body_repository import count_sr_report_body_rows

    db_rows = await asyncio.to_thread(count_sr_report_body_rows, report_id)

    logger.info(
        "[SRWorkflow] save_body 완료: saved_count={} db_sr_report_body_rows={} agent_success={} agent_msg={!r}",
        saved,
        db_rows,
        agent_ok,
        agent_msg[:500] if agent_msg else "",
    )
    if body_errors:
        logger.warning("[SRWorkflow] save_body 에이전트 errors ({}건): {}", len(body_errors), body_errors)
    if saved == 0 and agent_ok:
        logger.warning(
            "[SRWorkflow] save_body: saved_count=0 이지만 agent_success=True — map/save 미호출 가능성 확인"
        )

    return {
        "body_saved_count": saved,
        "body_agent_success": agent_ok,
        "body_agent_message": agent_msg or None,
        "body_agent_errors": body_errors if body_errors else None,
        "sr_report_body_db_row_count": db_rows,
    }


async def _save_images_node(state: SRWorkflowState) -> Dict[str, Any]:
    """노드 5: 이미지 에이전트(sr_images_agent) 호출 → parsing + 매핑·저장 (§10)."""
    from ..routing.agent_router import AgentRouter
    from backend.domain.v1.data_integration.hub.repositories.sr_report_images_repository import (
        count_sr_report_images_rows,
    )

    pdf_bytes = state.get("pdf_bytes")
    report_id = state.get("report_id")
    index_page_numbers = state.get("index_page_numbers")
    if index_page_numbers is None and report_id:
        index_page_numbers = await asyncio.to_thread(
            _load_index_page_numbers_from_db, report_id
        )

    if not pdf_bytes or not report_id:
        logger.warning("[SRWorkflow] save_images: pdf_bytes 또는 report_id 없음")
        return {}

    img_dir = state.get("image_output_dir")
    base_name = state.get("image_base_name")

    router = AgentRouter()
    result = await router.route_to(
        agent_name="sr_images_agent",
        pdf_bytes=pdf_bytes,
        report_id=report_id,
        index_page_numbers=index_page_numbers,
        image_output_dir=img_dir,
        base_name=base_name,
    )
    saved = int(result.get("saved_count", 0) or 0)
    agent_ok = bool(result.get("success"))
    agent_msg = (result.get("message") or "").strip()
    raw_errs = result.get("errors")
    img_errors: List[Dict[str, Any]] = []
    if isinstance(raw_errs, list):
        img_errors = [e for e in raw_errs if isinstance(e, dict)]
    elif raw_errs:
        img_errors = [{"detail": str(raw_errs)}]

    db_rows = await asyncio.to_thread(count_sr_report_images_rows, report_id)

    logger.info(
        "[SRWorkflow] save_images 완료: saved_count={} db_sr_report_images_rows={} agent_ok={}",
        saved,
        db_rows,
        agent_ok,
    )
    if not agent_ok:
        logger.warning(
            "[SRWorkflow] save_images 에이전트 실패: message={} errors={}",
            agent_msg or "(없음)",
            img_errors or raw_errs,
        )
    elif img_errors:
        logger.warning("[SRWorkflow] save_images 에이전트 errors ({}건): {}", len(img_errors), img_errors)

    vlm_auto: Dict[str, Any] = {}
    if agent_ok and saved > 0 and report_id:
        from backend.domain.v1.data_integration.spokes.infra.sr_image_vlm_enrichment import (
            maybe_auto_enrich_after_image_save,
        )

        vlm_result = await asyncio.to_thread(maybe_auto_enrich_after_image_save, str(report_id))
        if vlm_result is not None:
            vlm_auto = {
                "images_vlm_auto_success": bool(vlm_result.get("success")),
                "images_vlm_auto_message": str(vlm_result.get("message", "")) or None,
                "images_vlm_auto_updated": int(vlm_result.get("updated", 0) or 0),
                "images_vlm_auto_skipped": int(vlm_result.get("skipped", 0) or 0),
            }
            logger.info(
                "[SRWorkflow] save_images VLM 자동 보강: success={} updated={} skipped={}",
                vlm_auto.get("images_vlm_auto_success"),
                vlm_auto.get("images_vlm_auto_updated"),
                vlm_auto.get("images_vlm_auto_skipped"),
            )

    return {
        "images_saved_count": saved,
        "images_agent_success": agent_ok,
        "images_agent_message": agent_msg or None,
        "images_agent_errors": img_errors if img_errors else None,
        "sr_report_images_db_row_count": db_rows,
        **vlm_auto,
    }


async def _parse_only_node(state: SRWorkflowState) -> Dict[str, Any]:
    """DB 저장 없이 메타+인덱스만 파싱 (extract 확인용: historical_sr_reports, sr_report_index만)"""
    from ...models.states import SRParsingResult
    from backend.domain.shared.tool.parsing.pdf_metadata import parse_sr_report_metadata
    from backend.domain.shared.tool.sr_report_tools import parse_sr_report_index

    pdf_bytes = state.get("pdf_bytes")
    if not pdf_bytes:
        return {}
    company = state["company"]
    year = state["year"]
    company_id = state.get("company_id")

    parsing_result = SRParsingResult()
    meta_result = await asyncio.to_thread(
        parse_sr_report_metadata, pdf_bytes, company, year, company_id
    )
    if "error" in meta_result:
        parsing_result.error = meta_result["error"]
        return {"parsing_result": parsing_result.to_dict()}

    parsing_result.historical_sr_reports = meta_result.get("historical_sr_reports")
    report_id = parsing_result.historical_sr_reports["id"]
    index_page_numbers = parsing_result.historical_sr_reports.get("index_page_numbers") or []

    if index_page_numbers:
        index_result = await asyncio.to_thread(
            parse_sr_report_index, pdf_bytes, report_id, index_page_numbers
        )
        if "error" not in index_result:
            parsing_result.sr_report_index = index_result.get("sr_report_index", [])

    out = parsing_result.to_dict()
    out.pop("sr_report_body", None)
    out.pop("sr_report_images", None)
    logger.info("[SRWorkflow] parse_only 노드: 메타+인덱스 파싱 완료 (DB 저장 안 함)")
    return {"parsing_result": out}


def _route_after_save_metadata(
    state: SRWorkflowState,
) -> Literal["save_index", "save_body", "save_images", "__end__"]:
    """save_metadata 이후: only_step에 따라 해당 노드로, metadata면 END."""
    only = state.get("only_step")
    if only == "metadata":
        return "__end__"
    if only == "body":
        return "save_body"
    if only == "images":
        return "save_images"
    return "save_index"


def _route_after_save_index(state: SRWorkflowState) -> Literal["save_body", "__end__"]:
    """save_index 이후: only_step이 index면 END, 아니면 save_body."""
    if state.get("only_step") == "index":
        return "__end__"
    return "save_body"


def _route_after_save_body(state: SRWorkflowState) -> Literal["save_images", "__end__"]:
    """save_body 이후: only_step이 body면 END, 아니면 save_images."""
    if state.get("only_step") == "body":
        return "__end__"
    return "save_images"


def build_sr_workflow():
    """SR 워크플로우 그래프 빌드 및 컴파일.
    상태 전달: SRWorkflowState (models.langgraph)
    """
    if not LANGGRAPH_AVAILABLE:
        raise ImportError("langgraph가 필요합니다. pip install langgraph")

    workflow = StateGraph(SRWorkflowState)

    workflow.add_node("fetch_and_parse", _fetch_and_parse_node)
    workflow.add_node("save_metadata", _save_metadata_node)
    workflow.add_node("save_index", _save_index_node)
    workflow.add_node("save_body", _save_body_node)
    workflow.add_node("save_images", _save_images_node)
    workflow.add_node("parse_only", _parse_only_node)

    workflow.set_entry_point("fetch_and_parse")
    workflow.add_conditional_edges(
        "fetch_and_parse",
        _route_after_fetch,
        {
            "save_metadata": "save_metadata",
            "save_index": "save_index",
            "save_body": "save_body",
            "save_images": "save_images",
            "parse_only": "parse_only",
            "end": END,
        },
    )
    workflow.add_conditional_edges(
        "save_metadata",
        _route_after_save_metadata,
        {
            "save_index": "save_index",
            "save_body": "save_body",
            "save_images": "save_images",
            "__end__": END,
        },
    )
    workflow.add_conditional_edges(
        "save_index",
        _route_after_save_index,
        {"save_body": "save_body", "__end__": END},
    )
    workflow.add_conditional_edges(
        "save_body",
        _route_after_save_body,
        {"save_images": "save_images", "__end__": END},
    )
    workflow.add_edge("save_images", END)
    workflow.add_edge("parse_only", END)

    return workflow.compile()


# 싱글톤 그래프 인스턴스 (필요 시 사용)
_compiled_graph = None


def get_sr_graph():
    """컴파일된 SR 그래프 반환 (캐시)."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_sr_workflow()
    return _compiled_graph
