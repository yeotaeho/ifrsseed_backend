"""sr_report_images 테이블 모델 (이미지 구조화 저장)"""
from __future__ import annotations

import uuid
from sqlalchemy import Column, Text, Integer, ForeignKey, LargeBinary
from sqlalchemy.dialects.postgresql import UUID, JSONB, NUMERIC
from sqlalchemy.sql import func
from sqlalchemy.types import TIMESTAMP

try:
    from ifrs_agent.database.base import Base
except ImportError:
    from backend.domain.v1.ifrs_agent.database.base import Base


class SrReportImage(Base):
    """sr_report_images (추출된 이미지 메타)"""
    __tablename__ = "sr_report_images"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_id = Column(UUID(as_uuid=True), ForeignKey("historical_sr_reports.id", ondelete="CASCADE"), nullable=False, index=True)
    page_number = Column(Integer, nullable=False)
    image_index = Column(Integer, nullable=True)
    # 선택: 메모리/Blob 모드에서 래스터 바이너리 (PostgreSQL BYTEA)
    image_blob = Column(LargeBinary, nullable=True)
    image_width = Column(Integer, nullable=True)
    image_height = Column(Integer, nullable=True)
    image_type = Column(Text, nullable=True)
    caption_text = Column(Text, nullable=True)
    caption_confidence = Column(NUMERIC(5, 2), nullable=True)
    extracted_data = Column(JSONB, nullable=True)
    caption_embedding_id = Column(Text, nullable=True)
    embedding_status = Column(Text, server_default="pending", nullable=True)
    extracted_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
