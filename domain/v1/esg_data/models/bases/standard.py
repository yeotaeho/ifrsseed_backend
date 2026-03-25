"""Standard ORM (standards)."""

from sqlalchemy import Column, String, Text, Boolean, TIMESTAMP, ARRAY, Date
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from backend.core.db import Base
from backend.domain.v1.esg_data.models.bases._embedding import vector_column


class Standard(Base):
    """기준서 테이블 (섹션별 row)."""

    __tablename__ = "standards"

    standard_id = Column(String(50), primary_key=True)
    section_name = Column(String(200), primary_key=True)

    standard_name = Column(String(200), nullable=False)
    version = Column(String(20))
    effective_date = Column(Date)

    section_content = Column(Text, nullable=False)
    section_type = Column(String(50))
    paragraph_reference = Column(String(50))

    validation_rules = Column(JSONB)
    key_terms = Column(ARRAY(String))
    related_concepts = Column(ARRAY(String))

    is_active = Column(Boolean, default=True, server_default="true")
    created_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
    )
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    section_embedding = Column(vector_column(1024), nullable=True)
    section_embedding_text = Column(Text, nullable=True)
    section_embedding_updated_at = Column(TIMESTAMP(timezone=True), nullable=True)
