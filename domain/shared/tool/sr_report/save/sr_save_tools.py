"""LLM 기반 SR 파싱 결과 저장 도구 (LangChain Tools)

4개 테이블(historical_sr_reports, sr_report_index, sr_report_body, sr_report_images)에
저장하는 도구를 LangChain Tool로 제공하여 LLM이 호출할 수 있도록 합니다.
"""
from __future__ import annotations

import base64
import uuid
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool
from loguru import logger

try:
    from ifrs_agent.database.base import get_session
except ImportError:
    from backend.domain.v1.ifrs_agent.database.base import get_session

from backend.domain.v1.data_integration.models.bases import (
    HistoricalSRReport,
    SrReportIndex,
    SrReportBody,
    SrReportImage,
)


def _decode_optional_image_blob_base64(b64: Optional[str]) -> Optional[bytes]:
    """LangChain 도구는 바이트 대신 base64 문자열로 선택 전달."""
    if not b64 or not isinstance(b64, str):
        return None
    try:
        return base64.b64decode(b64.strip())
    except Exception:
        return None


def _to_uuid(value: Any) -> uuid.UUID:
    """문자열을 UUID로 변환"""
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return uuid.uuid4()


@tool
def save_historical_sr_report(
    company_id: Optional[str],
    report_year: int,
    report_name: str,
    source: str,
    total_pages: int,
    index_page_numbers: List[int],
) -> str:
    """
    historical_sr_reports 테이블에 보고서 메타데이터 1건을 저장합니다.
    
    Args:
        company_id: companies.id (UUID 문자열 또는 None)
        report_year: 보고서 연도
        report_name: 보고서 이름
        source: 출처 (예: "sr_agent")
        total_pages: 총 페이지 수
        index_page_numbers: 인덱스 페이지 번호 목록
    
    Returns:
        저장된 report_id (UUID 문자열)
    """
    session = get_session()
    try:
        report_id = uuid.uuid4()
        cid = _to_uuid(company_id) if company_id else None
        
        entity = HistoricalSRReport(
            id=report_id,
            company_id=cid,
            report_year=report_year,
            report_name=report_name,
            source=source,
            total_pages=total_pages,
            index_page_numbers=index_page_numbers,
        )
        session.add(entity)
        session.commit()
        session.refresh(entity)
        logger.info(f"[Tool] historical_sr_reports 저장: id={entity.id}, year={report_year}")
        return str(entity.id)
    except Exception as e:
        session.rollback()
        logger.error(f"[Tool] historical_sr_reports 저장 실패: {e}")
        raise
    finally:
        session.close()


@tool
def save_sr_report_index(
    report_id: str,
    index_type: str,
    dp_id: str,
    page_numbers: List[int],
    index_page_number: Optional[int] = None,
    dp_name: Optional[str] = None,
    section_title: Optional[str] = None,
    remarks: Optional[str] = None,
    parsing_method: str = "docling",
    confidence_score: Optional[float] = None,
) -> str:
    """
    sr_report_index 테이블에 DP → 페이지 매핑 1건을 저장합니다.
    
    Args:
        report_id: historical_sr_reports.id (UUID 문자열)
        index_type: "gri", "ifrs", "sasb" 중 하나
        dp_id: DP ID (예: "GRI-305-1", "S2-15-a")
        page_numbers: 해당 DP가 나오는 페이지 번호 목록
        index_page_number: 인덱스 페이지 번호 (선택)
        dp_name: DP 이름 (선택)
        section_title: 섹션 제목 (선택)
        remarks: 비고 (선택)
        parsing_method: 파싱 방법 (기본: "docling")
        confidence_score: 신뢰도 (0.0~1.0, 선택)
    
    Returns:
        저장된 index_id (UUID 문자열)
    """
    session = get_session()
    try:
        index_id = uuid.uuid4()
        entity = SrReportIndex(
            id=index_id,
            report_id=_to_uuid(report_id),
            index_type=index_type,
            index_page_number=index_page_number,
            dp_id=dp_id,
            dp_name=dp_name,
            page_numbers=page_numbers,
            section_title=section_title,
            remarks=remarks,
            parsing_method=parsing_method,
            confidence_score=confidence_score,
        )
        session.add(entity)
        session.commit()
        logger.info(f"[Tool] sr_report_index 저장: dp_id={dp_id}, pages={page_numbers}")
        return str(index_id)
    except Exception as e:
        session.rollback()
        logger.error(f"[Tool] sr_report_index 저장 실패: {e}")
        raise
    finally:
        session.close()


@tool
def save_sr_report_body(
    report_id: str,
    page_number: int,
    content_text: str,
    is_index_page: bool = False,
    content_type: Optional[str] = None,
    paragraphs: Optional[List[Dict[str, Any]]] = None,
    toc_path: Optional[List[str]] = None,
) -> str:
    """
    sr_report_body 테이블에 페이지별 본문 1건을 저장합니다.
    
    Args:
        report_id: historical_sr_reports.id (UUID 문자열)
        page_number: 페이지 번호
        content_text: 본문 텍스트
        is_index_page: 인덱스 페이지 여부 (기본: False)
        content_type: 콘텐츠 타입 (선택)
        paragraphs: 문단 목록 (선택, JSON)
        toc_path: 인쇄 목차 기준 계층 (선택), 문자열 배열 JSON 예: ["ESG PERFORMANCE","ENVIRONMENTAL","기후변화 대응"]
    
    Returns:
        저장된 body_id (UUID 문자열)
    """
    session = get_session()
    try:
        body_id = uuid.uuid4()
        entity = SrReportBody(
            id=body_id,
            report_id=_to_uuid(report_id),
            page_number=page_number,
            is_index_page=is_index_page,
            content_text=content_text,
            content_type=content_type,
            paragraphs=paragraphs or [],
            toc_path=toc_path,
            embedding_id=None,
            embedding_status="pending",
        )
        session.add(entity)
        session.commit()
        logger.info(f"[Tool] sr_report_body 저장: page={page_number}, len={len(content_text)}")
        return str(body_id)
    except Exception as e:
        session.rollback()
        logger.error(f"[Tool] sr_report_body 저장 실패: {e}")
        raise
    finally:
        session.close()


def save_sr_report_body_batch(
    report_id: str,
    bodies: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    sr_report_body 테이블에 페이지별 본문을 배치로 저장합니다.

    Args:
        report_id: historical_sr_reports.id (UUID 문자열)
        bodies: 본문 행 리스트. 각 항목은 page_number, content_text 필수,
                is_index_page, content_type, paragraphs, toc_path 선택.

    Returns:
        {"success": bool, "saved_count": int, "errors": list}
    """
    session = get_session()
    saved_count = 0
    errors: List[Dict[str, Any]] = []

    try:
        rid = _to_uuid(report_id)
        for idx, item in enumerate(bodies):
            try:
                page_number = int(item.get("page_number", 0))
                content_text = str(item.get("content_text", ""))
                entity = SrReportBody(
                    id=uuid.uuid4(),
                    report_id=rid,
                    page_number=page_number,
                    is_index_page=bool(item.get("is_index_page", False)),
                    content_text=content_text,
                    content_type=item.get("content_type"),
                    paragraphs=item.get("paragraphs"),
                    toc_path=item.get("toc_path"),
                    embedding_id=None,
                    embedding_status="pending",
                )
                session.add(entity)
                saved_count += 1
            except Exception as e:
                errors.append({"index": idx, "page_number": item.get("page_number"), "error": str(e)})
                logger.error(f"[Tool] sr_report_body 배치 저장 오류 (idx={idx}): {e}")

        session.commit()
        logger.info(f"[Tool] sr_report_body 배치 저장: {saved_count}건 성공, {len(errors)}건 실패")
        return {"success": True, "saved_count": saved_count, "errors": errors}
    except Exception as e:
        session.rollback()
        logger.error(f"[Tool] sr_report_body 배치 저장 실패: {e}")
        return {"success": False, "saved_count": saved_count, "errors": [{"error": str(e)}]}
    finally:
        session.close()


@tool
def save_sr_report_index_batch(
    report_id: str,
    indices: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    sr_report_index 테이블에 DP → 페이지 매핑을 배치로 저장합니다.
    report_id와 indices 둘 다 필수. indices는 validate/detect 단계에서 다룬 인덱스 배열 전체를 반드시 전달 (생략 금지).

    Args:
        report_id: historical_sr_reports.id (UUID 문자열)
        indices: (필수) 인덱스 리스트 전체. 각 항목은 아래 필드를 포함:
            - index_type: "gri", "ifrs", "sasb" 중 하나 (필수)
            - dp_id: DP ID (필수, 예: "GRI-305-1", "S2-15-a")
            - page_numbers: 페이지 번호 목록 (필수)
            - index_page_number: 인덱스 페이지 번호 (선택)
            - dp_name: DP 이름 (선택)
            - section_title: 섹션 제목 (선택)
            - remarks: 비고 (선택)
            - parsing_method: 파싱 방법 (선택, 기본: "docling")
            - confidence_score: 신뢰도 (선택)
    
    Returns:
        {"success": bool, "saved_count": int, "errors": list}
    """
    session = get_session()
    saved_count = 0
    errors = []
    
    try:
        rid = _to_uuid(report_id)
        
        for idx, item in enumerate(indices):
            try:
                index_id = uuid.uuid4()
                entity = SrReportIndex(
                    id=index_id,
                    report_id=rid,
                    index_type=item.get("index_type"),
                    index_page_number=item.get("index_page_number"),
                    dp_id=item.get("dp_id"),
                    dp_name=item.get("dp_name"),
                    page_numbers=item.get("page_numbers", []),
                    section_title=item.get("section_title"),
                    remarks=item.get("remarks"),
                    parsing_method=item.get("parsing_method", "docling"),
                    confidence_score=item.get("confidence_score"),
                )
                session.add(entity)
                saved_count += 1
            except Exception as e:
                errors.append({"index": idx, "dp_id": item.get("dp_id"), "error": str(e)})
                logger.error(f"[Tool] sr_report_index 배치 저장 오류 (idx={idx}): {e}")
        
        session.commit()
        logger.info(f"[Tool] sr_report_index 배치 저장: {saved_count}건 성공, {len(errors)}건 실패")
        return {"success": True, "saved_count": saved_count, "errors": errors}
    except Exception as e:
        session.rollback()
        logger.error(f"[Tool] sr_report_index 배치 저장 실패: {e}")
        return {"success": False, "saved_count": saved_count, "errors": [{"error": str(e)}]}
    finally:
        session.close()


def save_sr_report_images_batch(
    report_id: str,
    rows: List[Dict[str, Any]],
    *,
    replace_existing: bool = True,
) -> Dict[str, Any]:
    """
    sr_report_images 테이블에 이미지 메타를 배치 저장합니다.

    기본적으로 동일 report_id 기존 행을 모두 삭제한 뒤 삽입합니다(재실행 멱등).

    Args:
        report_id: historical_sr_reports.id (UUID 문자열)
        rows: 각 항목 page_number 필수;
              image_index, image_blob(bytes, 선택), image_width, image_height,
              image_type, caption_text, caption_confidence, extracted_data 선택.
        replace_existing: True면 저장 전 해당 report_id 행 전부 DELETE

    Returns:
        {"success": bool, "saved_count": int, "errors": list, "saved_rows": list[dict]}
    """
    session = get_session()
    saved_count = 0
    errors: List[Dict[str, Any]] = []
    saved_rows: List[Dict[str, Any]] = []

    try:
        rid = _to_uuid(report_id)
        if replace_existing:
            session.query(SrReportImage).filter(SrReportImage.report_id == rid).delete(
                synchronize_session=False
            )

        for idx, item in enumerate(rows):
            try:
                page_number = int(item.get("page_number", 0))
                image_id = uuid.uuid4()
                entity = SrReportImage(
                    id=image_id,
                    report_id=rid,
                    page_number=page_number,
                    image_index=item.get("image_index"),
                    image_blob=item.get("image_blob"),
                    image_width=item.get("image_width"),
                    image_height=item.get("image_height"),
                    image_type=item.get("image_type"),
                    caption_text=item.get("caption_text"),
                    caption_confidence=item.get("caption_confidence"),
                    extracted_data=item.get("extracted_data"),
                    caption_embedding_id=item.get("caption_embedding_id"),
                    embedding_status=item.get("embedding_status") or "pending",
                )
                session.add(entity)
                saved_count += 1
                saved_rows.append({
                    "id": str(image_id),
                    "report_id": str(report_id),
                    "page_number": page_number,
                    "image_index": item.get("image_index"),
                    "image_blob_len": len(item["image_blob"]) if item.get("image_blob") else None,
                    "image_width": item.get("image_width"),
                    "image_height": item.get("image_height"),
                    "image_type": item.get("image_type"),
                    "caption_text": item.get("caption_text"),
                })
            except Exception as e:
                errors.append({"index": idx, "page_number": item.get("page_number"), "error": str(e)})
                logger.error(f"[Tool] sr_report_images 배치 저장 오류 (idx={idx}): {e}")

        session.commit()
        logger.info(
            f"[Tool] sr_report_images 배치 저장: {saved_count}건 성공, {len(errors)}건 실패, replace={replace_existing}"
        )
        return {
            "success": True,
            "saved_count": saved_count,
            "errors": errors,
            "saved_rows": saved_rows,
        }
    except Exception as e:
        session.rollback()
        logger.error(f"[Tool] sr_report_images 배치 저장 실패: {e}")
        return {
            "success": False,
            "saved_count": saved_count,
            "errors": [{"error": str(e)}],
            "saved_rows": saved_rows,
        }
    finally:
        session.close()


@tool
def save_sr_report_image(
    report_id: str,
    page_number: int,
    image_index: Optional[int] = None,
    image_blob_base64: Optional[str] = None,
    image_width: Optional[int] = None,
    image_height: Optional[int] = None,
    image_type: Optional[str] = None,
    caption_text: Optional[str] = None,
) -> str:
    """
    sr_report_images 테이블에 이미지 메타 1건을 저장합니다.
    
    Args:
        report_id: historical_sr_reports.id (UUID 문자열)
        page_number: 페이지 번호
        image_index: 페이지 내 이미지 인덱스 (선택)
        image_blob_base64: 원본 이미지 바이트를 base64로 인코딩한 문자열 (선택, image_blob 컬럼)
        image_width: 너비 (선택)
        image_height: 높이 (선택)
        image_type: 이미지 타입 (선택)
        caption_text: 캡션 (선택)
    
    Returns:
        저장된 image_id (UUID 문자열)
    """
    session = get_session()
    try:
        image_id = uuid.uuid4()
        blob = _decode_optional_image_blob_base64(image_blob_base64)
        entity = SrReportImage(
            id=image_id,
            report_id=_to_uuid(report_id),
            page_number=page_number,
            image_index=image_index,
            image_blob=blob,
            image_width=image_width,
            image_height=image_height,
            image_type=image_type,
            caption_text=caption_text,
            caption_confidence=None,
            extracted_data=None,
            caption_embedding_id=None,
            embedding_status="pending",
        )
        session.add(entity)
        session.commit()
        logger.info(f"[Tool] sr_report_image 저장: page={page_number}, image_index={image_index}")
        return str(image_id)
    except Exception as e:
        session.rollback()
        logger.error(f"[Tool] sr_report_image 저장 실패: {e}")
        raise
    finally:
        session.close()


# 5개 도구를 리스트로 제공
SR_SAVE_TOOLS = [
    save_historical_sr_report,
    save_sr_report_index,
    save_sr_report_index_batch,
    save_sr_report_body,
    save_sr_report_image,
]
