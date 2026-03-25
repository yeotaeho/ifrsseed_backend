"""Service 모듈 — MappingSuggestionService는 esg_data 재구현 전 스텁(ifrs_agent.service)."""

from .embedding_service import EmbeddingService
from .embedding_text_service import EmbeddingTextService

__all__ = [
    "EmbeddingService",
    "EmbeddingTextService",
]
