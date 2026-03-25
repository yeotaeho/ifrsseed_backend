"""SR 파싱 결과 DB 저장 리포지토리 (방법 B-1: 하이브리드)

PyMuPDF로 추출한 SRParsingResult를 historical_sr_reports, sr_report_index,
sr_report_body, sr_report_images 4개 테이블에 저장합니다.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from loguru import logger

try:
    from ifrs_agent.database.base import get_session
except ImportError:
    from backend.domain.v1.ifrs_agent.database.base import get_session

from backend.domain.v1.data_integration.models.bases import (
    SrReportIndex,
    SrReportBody,
    SrReportImage,
)
from backend.domain.v1.data_integration.models.states import SRParsingResult
from .historical_sr_report_repository import HistoricalSRReportRepository


def _to_uuid(value: Any) -> Optional[uuid.UUID]:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


def _dict_to_sr_report_index(row: Dict[str, Any]) -> SrReportIndex:
    return SrReportIndex(
        id=_to_uuid(row.get("id")) or uuid.uuid4(),
        report_id=_to_uuid(row["report_id"]) or uuid.uuid4(),
        index_type=str(row.get("index_type", "")),
        index_page_number=row.get("index_page_number"),
        dp_id=str(row.get("dp_id", "")),
        dp_name=row.get("dp_name"),
        page_numbers=row.get("page_numbers") or [],
        section_title=row.get("section_title"),
        remarks=row.get("remarks"),
        parsing_method=row.get("parsing_method", "docling"),
        confidence_score=row.get("confidence_score"),
    )


def _dict_to_sr_report_body(row: Dict[str, Any]) -> SrReportBody:
    return SrReportBody(
        id=_to_uuid(row.get("id")) or uuid.uuid4(),
        report_id=_to_uuid(row["report_id"]) or uuid.uuid4(),
        page_number=int(row.get("page_number", 0)),
        is_index_page=bool(row.get("is_index_page", False)),
        content_text=str(row.get("content_text", "")),
        content_type=row.get("content_type"),
        paragraphs=row.get("paragraphs"),
        toc_path=row.get("toc_path"),
        embedding_id=row.get("embedding_id"),
        embedding_status=str(row.get("embedding_status", "pending")),
    )


def _dict_to_sr_report_image(row: Dict[str, Any]) -> SrReportImage:
    return SrReportImage(
        id=_to_uuid(row.get("id")) or uuid.uuid4(),
        report_id=_to_uuid(row["report_id"]) or uuid.uuid4(),
        page_number=int(row.get("page_number", 0)),
        image_index=row.get("image_index"),
        image_blob=row.get("image_blob"),
        image_width=row.get("image_width"),
        image_height=row.get("image_height"),
        image_type=row.get("image_type"),
        caption_text=row.get("caption_text"),
        caption_confidence=row.get("caption_confidence"),
        extracted_data=row.get("extracted_data"),
        caption_embedding_id=row.get("caption_embedding_id"),
        embedding_status=str(row.get("embedding_status", "pending")),
    )


class SRParsingResultRepository:
    """
    방법 B-1: SR 파싱 결과를 4개 테이블에 저장하는 리포지토리.
    HistoricalSRReportRepository로 메타 저장 후, index/body/images를 한 트랜잭션으로 저장.
    """

    def __init__(self):
        self._hist_repo = HistoricalSRReportRepository()

    def save_parsing_result(self, parsing_result: SRParsingResult) -> bool:
        """
        SRParsingResult를 DB 4개 테이블에 저장합니다.

        Returns:
            성공 시 True, 실패 시 False
        """
        if not parsing_result.is_success or not parsing_result.historical_sr_reports:
            logger.warning("save_parsing_result: 유효하지 않은 파싱 결과")
            return False

        hist_row = parsing_result.historical_sr_reports
        report_id = self._hist_repo.save(hist_row)
        if report_id is None:
            logger.error("historical_sr_reports 저장 실패")
            return False

        session = get_session()
        try:
            for row in parsing_result.sr_report_index:
                session.add(_dict_to_sr_report_index(row))
            for row in parsing_result.sr_report_body:
                session.add(_dict_to_sr_report_body(row))
            for row in parsing_result.sr_report_images:
                session.add(_dict_to_sr_report_image(row))
            session.commit()
            logger.info(
                f"sr_report_index={len(parsing_result.sr_report_index)}, "
                f"sr_report_body={len(parsing_result.sr_report_body)}, "
                f"sr_report_images={len(parsing_result.sr_report_images)} 저장 완료"
            )
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"sr_report_index/body/images 저장 실패: {e}")
            return False
        finally:
            session.close()
