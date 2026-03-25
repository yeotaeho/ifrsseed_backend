"""Glossary ORM (glossary)."""

from sqlalchemy import Column, String, Text, Integer, Boolean, TIMESTAMP, ARRAY
from sqlalchemy.sql import func

from backend.core.db import Base
from backend.domain.v1.esg_data.models.bases._embedding import vector_column


class Glossary(Base):
    """용어집 테이블 (독립 참조)."""

    __tablename__ = "glossary"

    term_id = Column(Integer, primary_key=True, autoincrement=True)
    term_ko = Column(String(200), nullable=False, unique=True)
    term_en = Column(String(200))

    definition_ko = Column(Text)
    definition_en = Column(Text)

    standard = Column(String(50), index=True)
    category = Column(String(50))

    related_dps = Column(ARRAY(String))
    related_terms = Column(ARRAY(String))
    source = Column(String(200))

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

    term_embedding = Column(vector_column(1024), nullable=True)
    term_embedding_text = Column(Text, nullable=True)
    term_embedding_updated_at = Column(TIMESTAMP(timezone=True), nullable=True)


SynonymGlossary = Glossary
