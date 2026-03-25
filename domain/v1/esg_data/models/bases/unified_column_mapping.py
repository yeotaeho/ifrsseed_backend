"""UnifiedColumnMapping ORM (unified_column_mappings)."""

from sqlalchemy import (
    Column,
    String,
    Text,
    Float,
    Boolean,
    TIMESTAMP,
    ForeignKey,
    CheckConstraint,
    ARRAY,
)
from sqlalchemy.dialects.postgresql import JSONB, ENUM as PG_ENUM
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from backend.core.db import Base
from backend.domain.v1.esg_data.models.bases._embedding import vector_column


class UnifiedColumnMapping(Base):
    """통합 컬럼 매핑 테이블."""

    __tablename__ = "unified_column_mappings"

    unified_column_id = Column(String(50), primary_key=True)
    column_name_ko = Column(String(200), nullable=False)
    column_name_en = Column(String(200), nullable=False)
    column_description = Column(Text)

    column_category = Column(String(1), nullable=False)
    column_topic = Column(String(100))
    column_subtopic = Column(String(100))

    primary_standard = Column(String(50), index=True)
    primary_rulebook_id = Column(
        String(50),
        ForeignKey("rulebooks.rulebook_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    applicable_standards = Column(ARRAY(String))

    mapped_dp_ids = Column(ARRAY(String), nullable=False)

    mapping_confidence = Column(Float)
    mapping_notes = Column(Text)
    rulebook_conflicts = Column(JSONB)

    column_type = Column(
        PG_ENUM(
            "quantitative",
            "qualitative",
            "narrative",
            "binary",
            name="unified_column_type_enum",
            create_type=False,
        ),
        nullable=False,
    )
    unit = Column(String(50))

    validation_rules = Column(JSONB, default={}, server_default="{}")
    value_range = Column(JSONB)

    financial_linkages = Column(ARRAY(String))
    financial_impact_type = Column(String(50))

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
    reporting_frequency = Column(String(20))

    unified_embedding = Column(vector_column(1024), nullable=True)

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

    primary_rulebook = relationship("Rulebook", backref="unified_mappings")

    __table_args__ = (
        CheckConstraint(
            "column_category IN ('E', 'S', 'G')",
            name="chk_unified_column_category",
        ),
    )
