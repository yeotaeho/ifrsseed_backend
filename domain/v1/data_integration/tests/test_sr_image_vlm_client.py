"""sr_image_vlm_client 단위 테스트 (API 미호출)."""
from __future__ import annotations

from backend.domain.v1.data_integration.spokes.infra.sr_image_vlm_client import (
    ALLOWED_IMAGE_TYPES,
    DEFAULT_VLM_MODEL,
    normalize_image_type,
)


def test_normalize_image_type() -> None:
    assert normalize_image_type("CHART") == "chart"
    assert normalize_image_type("unknown") == "unknown"
    assert normalize_image_type("not_a_type") == "unknown"
    assert normalize_image_type(None) == "unknown"


def test_allowed_set() -> None:
    assert "chart" in ALLOWED_IMAGE_TYPES
    assert "unknown" in ALLOWED_IMAGE_TYPES


def test_default_vlm_model_constant() -> None:
    assert DEFAULT_VLM_MODEL == "gpt-5-mini"
