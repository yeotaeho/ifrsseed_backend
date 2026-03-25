"""DataPoint ORM (data_points)."""

from sqlalchemy import (
    Column,
    String,
    Text,
    Boolean,
    TIMESTAMP,
    ForeignKey,
    CheckConstraint,
    ARRAY,
)
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from backend.core.db import Base
from backend.domain.v1.esg_data.models.bases._embedding import vector_column


class DataPoint(Base):
    """Data Point 테이블."""

    __tablename__ = "data_points"

    dp_id = Column(String(50), primary_key=True)
    dp_code = Column(String(100), nullable=False, unique=True)

    name_ko = Column(String(200), nullable=False)
    name_en = Column(String(200), nullable=False)
    description = Column(Text)

    standard = Column(String(50), nullable=False, index=True)
    category = Column(String(1), nullable=False)
    topic = Column(String(100), index=True)
    subtopic = Column(String(100))

    dp_type = Column(
        PG_ENUM(
            "quantitative",
            "qualitative",
            "narrative",
            "binary",
            name="dp_type_enum",
            create_type=False,
        ),
        nullable=False,
    )
    unit = Column(
        PG_ENUM(
            "percentage",
            "count",
            "currency_krw",
            "currency_usd",
            "tco2e",
            "mwh",
            "cubic_meter",
            "text",
            name="dp_unit_enum",
            create_type=False,
        ),
        nullable=True,
    )

    equivalent_dps = Column(ARRAY(String))
    parent_indicator = Column(
        String(50),
        ForeignKey("data_points.dp_id"),
        nullable=True,
        index=True,
    )
    child_dps = Column(ARRAY(String))

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

    is_active = Column(Boolean, default=True, server_default="true")
    deleted_at = Column(TIMESTAMP(timezone=True), nullable=True)
    deleted_by = Column(String(100), nullable=True)

    created_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
    )
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    embedding = Column(vector_column(1024), nullable=True)
    embedding_text = Column(Text, nullable=True)
    embedding_updated_at = Column(TIMESTAMP(timezone=True), nullable=True)

    parent = relationship(
        "DataPoint",
        remote_side=[dp_id],
        backref="children",
    )

    __table_args__ = (
        CheckConstraint("category IN ('E', 'S', 'G')", name="chk_category"),
    )
