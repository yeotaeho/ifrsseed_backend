"""historical_sr_reports 저장/조회 리포지토리"""
from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from loguru import logger

try:
    from ifrs_agent.database.base import get_session
except ImportError:
    from backend.domain.v1.ifrs_agent.database.base import get_session

from backend.domain.v1.data_integration.models.bases import HistoricalSRReport


class HistoricalSRReportRepository:
    """historical_sr_reports 테이블 접근"""

    def __init__(self, db_session=None):
        self._session = db_session
        self._owns_session = db_session is None

    def _get_session(self):
        if self._session is not None:
            return self._session
        return get_session()

    def save(self, row: Dict[str, Any]) -> Optional[uuid.UUID]:
        """
        파싱 결과 1건을 DB에 저장(insert)합니다.
        row: parsing_result["historical_sr_reports"] 형태의 dict.

        Returns:
            저장된 행의 id (UUID), 실패 시 None
        """
        session = self._get_session()
        try:
            report_id = row.get("id")
            if isinstance(report_id, str):
                report_id = uuid.UUID(report_id)
            elif report_id is None:
                report_id = uuid.uuid4()

            company_id = row.get("company_id")
            if company_id is not None and isinstance(company_id, str):
                company_id = uuid.UUID(company_id)

            entity = HistoricalSRReport(
                id=report_id,
                company_id=company_id,
                report_year=int(row["report_year"]),
                report_name=str(row["report_name"]),
                source=str(row.get("source", "sr_agent")),
                total_pages=row.get("total_pages"),
                index_page_numbers=row.get("index_page_numbers"),
            )
            session.add(entity)
            session.commit()
            session.refresh(entity)
            logger.info(f"historical_sr_reports 저장: id={entity.id}, report_year={entity.report_year}")
            return entity.id
        except Exception as e:
            session.rollback()
            logger.error(f"historical_sr_reports 저장 실패: {e}")
            return None
        finally:
            if self._owns_session and session is not None:
                session.close()
