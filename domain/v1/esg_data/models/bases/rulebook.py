"""Rulebook ORM (rulebooks)."""

from sqlalchemy import (
    Column,
    String,
    Text,
    Boolean,
    TIMESTAMP,
    ForeignKey,
    UniqueConstraint,
    ARRAY,
    Date,
)
from sqlalchemy.dialects.postgresql import JSONB, ENUM as PG_ENUM
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from backend.core.db import Base
from backend.domain.v1.esg_data.models.bases._embedding import vector_column


class Rulebook(Base):
    """Rulebook 테이블 (기준서별 공시 요구사항 상세)."""

    __tablename__ = "rulebooks"

    rulebook_id = Column(String(200), primary_key=True)

    standard_id = Column(String(50), nullable=False, index=True)

    primary_dp_id = Column(
        String(50),
        ForeignKey("data_points.dp_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    section_name = Column(String(200), nullable=False)
    rulebook_title = Column(String(300))
    rulebook_content = Column(Text)
    paragraph_reference = Column(String(50))

    validation_rules = Column(JSONB)
    key_terms = Column(ARRAY(String))
    related_concepts = Column(ARRAY(String))

    related_dp_ids = Column(ARRAY(String), nullable=True)

    disclosure_requirement = Column(
        PG_ENUM(
            "필수",
            "권장",
            "선택",
            "조건부",
            name="disclosure_requirement_enum",
            create_type=False,
        ),
        nullable=True,
    )
    is_primary = Column(Boolean, default=False)

    version = Column(String(20))
    effective_date = Column(Date)
    conflicts_with = Column(ARRAY(String))
    mapping_notes = Column(Text)

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

    primary_data_point = relationship("DataPoint", backref="primary_rulebooks")

    __table_args__ = (
        UniqueConstraint(
            "standard_id",
            "section_name",
            name="uq_rulebook_standard_section",
        ),
    )
