"""historical_sr_reports 테이블 모델 (SR 보고서 메타데이터)"""
from __future__ import annotations

import uuid
from sqlalchemy import Column, Text, Integer
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.sql import func
from sqlalchemy.types import TIMESTAMP

try:
    from ifrs_agent.database.base import Base
except ImportError:
    from backend.domain.v1.ifrs_agent.database.base import Base


class HistoricalSRReport(Base):
    """지속가능경영보고서 메타데이터 (historical_sr_reports)"""
    __tablename__ = "historical_sr_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    report_year = Column(Integer, nullable=False, index=True)
    report_name = Column(Text, nullable=False)
    source = Column(Text, nullable=False)
    total_pages = Column(Integer, nullable=True)
    index_page_numbers = Column(ARRAY(Integer), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
