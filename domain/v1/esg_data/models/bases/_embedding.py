"""pgvector 선택 의존 — 임베딩 컬럼 타입."""

try:
    from pgvector.sqlalchemy import Vector as _Vector  # type: ignore[import-not-found]
except ImportError:
    _Vector = None


def vector_column(dim: int = 1024):
    from sqlalchemy import Text

    return _Vector(dim) if _Vector is not None else Text
