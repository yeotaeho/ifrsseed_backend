"""sr_image_mapping 단위 테스트."""
from __future__ import annotations

import pytest

from backend.domain.shared.tool.sr_report.images import map_extracted_images_to_sr_report_rows


def test_map_extracted_images_to_rows_orders_by_page() -> None:
    rid = "00000000-0000-0000-0000-000000000099"
    by_page = {
        3: [
            {
                "path": "/tmp/a.png",
                "width": 10,
                "height": 20,
                "size_bytes": 100,
                "image_index": 0,
                "mime_type": "image/png",
            }
        ],
        1: [
            {"path": "/tmp/b.png", "width": 5, "height": 5, "size_bytes": 50, "image_index": 0},
            {"path": "/tmp/c.png", "width": 5, "height": 5, "size_bytes": 51, "image_index": 1},
        ],
    }
    rows = map_extracted_images_to_sr_report_rows(rid, by_page)
    assert len(rows) == 3
    assert rows[0]["page_number"] == 1
    assert rows[0]["image_index"] == 0
    assert rows[1]["page_number"] == 1
    assert rows[1]["image_index"] == 1
    assert rows[2]["page_number"] == 3
    assert rows[2].get("extracted_data", {}).get("size_bytes") == 100
    assert rows[2].get("extracted_data", {}).get("mime_type") == "image/png"


def test_memory_mode_persists_image_blob_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """SR_IMAGE_STORAGE=memory 이고 SR_IMAGE_PERSIST_BLOB 미설정이면 image_bytes → image_blob."""
    monkeypatch.setenv("SR_IMAGE_STORAGE", "memory")
    monkeypatch.delenv("SR_IMAGE_PERSIST_BLOB", raising=False)
    rid = "00000000-0000-0000-0000-000000000099"
    by_page = {
        1: [
            {
                "image_bytes": b"\x89PNG\r\n",
                "mime_type": "image/png",
                "width": 10,
                "height": 10,
                "size_bytes": 8,
                "image_index": 0,
            }
        ]
    }
    rows = map_extracted_images_to_sr_report_rows(rid, by_page)
    assert len(rows) == 1
    assert rows[0].get("image_blob") == b"\x89PNG\r\n"


def test_persist_blob_off_skips_bytea(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SR_IMAGE_STORAGE", "memory")
    monkeypatch.setenv("SR_IMAGE_PERSIST_BLOB", "0")
    rid = "00000000-0000-0000-0000-000000000099"
    by_page = {1: [{"image_bytes": b"x", "image_index": 0, "size_bytes": 1}]}
    rows = map_extracted_images_to_sr_report_rows(rid, by_page)
    assert "image_blob" not in rows[0]
