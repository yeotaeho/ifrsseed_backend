"""추출된 이미지 메타 → sr_report_images 배치 저장용 dict 리스트."""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional


def _should_persist_image_blob() -> bool:
    """BYTEA 저장 여부. 명시 끔(0)만 아니면 SR_IMAGE_STORAGE=memory 일 때 기본 켬(VLM·재조회용)."""
    v = os.getenv("SR_IMAGE_PERSIST_BLOB", "").strip().lower()
    if v in ("0", "false", "no", "off"):
        return False
    if v in ("1", "true", "yes", "on"):
        return True
    mode = os.getenv("SR_IMAGE_STORAGE", "memory").strip().lower()
    return mode == "memory"


def _optional_image_blob_from_item(item: Dict[str, Any]) -> Optional[bytes]:
    """`image_bytes`가 있고 보강 정책이 켜져 있으면 image_blob 컬럼용 bytes 반환."""
    if not _should_persist_image_blob():
        return None
    raw = item.get("image_bytes") or item.get("image_blob")
    if not raw or not isinstance(raw, (bytes, bytearray)):
        return None
    max_b = os.getenv("SR_IMAGE_MAX_BLOB_BYTES", "").strip()
    max_bytes = int(max_b) if max_b.isdigit() else 5_000_000
    if len(raw) > max_bytes:
        return None
    return bytes(raw)


def map_extracted_images_to_sr_report_rows(
    report_id: str,
    images_by_page: Dict[int, List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """
    extract_report_images 의 images_by_page 를 DB 저장용 행으로 변환합니다.

    Args:
        report_id: historical_sr_reports.id (문자열)
        images_by_page: { page_number: [ { path 또는 image_bytes, width, height, size_bytes, image_index, mime_type }, ... ] }
        (`path`는 미사용. `image_bytes`는 SR_IMAGE_STORAGE=memory 이고 SR_IMAGE_PERSIST_BLOB 미설정/1 일 때 `image_blob` 저장)

    Returns:
        save_sr_report_images_batch 에 넘길 dict 리스트.
    """
    _ = report_id  # 행 본문에는 포함하지 않음 (저장 시 FK로 전달)
    rows: List[Dict[str, Any]] = []
    for page_number in sorted(images_by_page.keys()):
        for item in images_by_page[page_number]:
            ed = item.get("extracted_data")
            mime = item.get("mime_type")
            if mime:
                if ed is None:
                    ed = {"mime_type": mime}
                elif isinstance(ed, dict):
                    ed = {**ed, "mime_type": mime}
            sb = item.get("size_bytes")
            if sb is not None:
                if ed is None:
                    ed = {"size_bytes": sb}
                elif isinstance(ed, dict):
                    ed = {**ed, "size_bytes": sb}
            row = {
                "page_number": int(page_number),
                "image_index": int(item.get("image_index", 0)),
                "image_width": item.get("width"),
                "image_height": item.get("height"),
                "image_type": item.get("image_type"),
                "caption_text": item.get("caption_text"),
                "caption_confidence": item.get("caption_confidence"),
                "extracted_data": ed,
            }
            blob = _optional_image_blob_from_item(item)
            if blob is not None:
                row["image_blob"] = blob
            rows.append(row)
    return rows
