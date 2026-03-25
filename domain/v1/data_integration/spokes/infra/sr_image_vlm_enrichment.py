"""sr_report_images 행에 대해 VLM으로 image_type / caption / confidence 보강 (UPDATE).

모델은 `sr_image_vlm_client.DEFAULT_VLM_MODEL`(gpt-5-mini) 고정. VLM은 항상 활성(엔드포인트 호출 시).

저장(추출) 파이프라인과 분리된 2단계. 이미지 바이트가 없으면 해당 행은 스킵.

자동 보강: `maybe_auto_enrich_after_image_save` — 이미지 저장 직후 워크플로/API에서 호출.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from backend.core.config.settings import get_settings
from backend.domain.v1.data_integration.models.bases import SrReportImage
from backend.domain.v1.data_integration.spokes.infra.sr_image_vlm_client import vlm_describe_image

try:
    from ifrs_agent.database.base import get_session
except ImportError:
    from backend.domain.v1.ifrs_agent.database.base import get_session


def _mime_from_extracted_data(ed: Any) -> str:
    if not isinstance(ed, dict):
        return "image/png"
    m = ed.get("mime_type")
    if isinstance(m, str) and m.strip():
        return m.strip()
    return "image/png"


def load_image_bytes_for_row(row: SrReportImage) -> Optional[Tuple[bytes, str]]:
    """
    VLM 입력용 (bytes, mime). 없으면 None.

    우선순위: image_blob → extracted_data.storage=s3 (bucket/key).
    """
    if row.image_blob:
        return row.image_blob, _mime_from_extracted_data(row.extracted_data)

    ed = row.extracted_data
    if isinstance(ed, dict) and ed.get("storage") == "s3":
        bucket = ed.get("bucket")
        key = ed.get("key")
        if isinstance(bucket, str) and isinstance(key, str) and bucket.strip() and key.strip():
            try:
                from backend.domain.v1.data_integration.spokes.infra.sr_image_object_storage import (
                    download_sr_object_bytes,
                )

                raw = download_sr_object_bytes(bucket=bucket.strip(), key=key.strip())
                return raw, _mime_from_extracted_data(ed)
            except Exception as e:
                logger.warning(
                    "[VLM enrich] S3 다운로드 실패 id={} key={}: {}",
                    row.id,
                    key,
                    e,
                )
                return None

    return None


def enrich_sr_report_images_vlm(
    report_id: str,
    *,
    model: Optional[str] = None,
    skip_if_caption_set: bool = False,
) -> Dict[str, Any]:
    """
    report_id에 속한 sr_report_images 행을 순회하며 VLM으로 메타 보강.

    DB 세션은 **행마다** 짧게 열고 커밋합니다. 한 세션으로 VLM(수 분)만 호출하면
    Neon 등에서 유휴 SSL 연결이 끊겨 마지막 commit 시 OperationalError가 날 수 있음.

    Returns:
      success, message, processed, updated, skipped, errors (list)
    """
    try:
        rid = uuid.UUID(str(report_id).strip())
    except (ValueError, TypeError) as e:
        return {
            "success": False,
            "message": f"invalid report_id: {e}",
            "processed": 0,
            "updated": 0,
            "skipped": 0,
            "errors": [{"error": str(e)}],
        }

    errors: List[Dict[str, Any]] = []
    processed = 0
    updated = 0
    skipped = 0

    q = get_session()
    try:
        id_rows = (
            q.query(SrReportImage.id)
            .filter(SrReportImage.report_id == rid)
            .order_by(SrReportImage.page_number, SrReportImage.image_index)
            .all()
        )
        row_ids = [r[0] for r in id_rows]
    finally:
        q.close()

    for row_id in row_ids:
        session = get_session()
        try:
            row = session.query(SrReportImage).filter(SrReportImage.id == row_id).one_or_none()
            if not row:
                continue
            processed += 1
            if skip_if_caption_set and row.caption_text and str(row.caption_text).strip():
                skipped += 1
                continue

            loaded = load_image_bytes_for_row(row)
            if not loaded:
                skipped += 1
                logger.debug("[VLM enrich] 바이트 없음, 스킵 id={}", row.id)
                continue

            raw, mime = loaded
            try:
                out = vlm_describe_image(raw, mime, model=model)
            except Exception as e:
                logger.warning("[VLM enrich] API 실패 id={}: {}", row.id, e)
                errors.append({"id": str(row.id), "error": str(e)})
                continue

            row.image_type = out.get("image_type")
            row.caption_text = out.get("caption_text")
            row.caption_confidence = out.get("caption_confidence")
            session.commit()
            updated += 1
        except Exception as e:
            session.rollback()
            logger.warning("[VLM enrich] DB 커밋 실패 id={}: {}", row_id, e)
            errors.append({"id": str(row_id), "error": str(e)})
        finally:
            session.close()

    msg = f"VLM 보강 완료: updated={updated}, skipped={skipped}, processed={processed}"
    if errors:
        msg += f" (오류 {len(errors)}건)"
    ok = len(errors) == 0
    logger.info("[VLM enrich] report_id={} success={} {}", report_id, ok, msg)
    return {
        "success": ok,
        "message": msg,
        "processed": processed,
        "updated": updated,
        "skipped": skipped,
        "errors": errors if errors else None,
    }


def vlm_enrichment_enabled() -> bool:
    """호환용. VLM은 코드상 항상 사용 가능(모델·스위치는 env가 아닌 하드코딩)."""
    return True


def maybe_auto_enrich_after_image_save(report_id: str) -> Optional[Dict[str, Any]]:
    """
    이미지 배치 저장 직후 자동 VLM 보강.

    - `SR_IMAGE_VLM_AUTO_AFTER_SAVE=0|false|off` 이면 스킵 (기본은 켬).
    - `OPENAI_API_KEY` 없으면 스킵 (로그만).
    - 그 외 `enrich_sr_report_images_vlm` 실행.
    """
    if not get_settings().sr_image_vlm_auto_after_save:
        logger.debug("[VLM auto] SR_IMAGE_VLM_AUTO_AFTER_SAVE 꺼짐, 스킵")
        return None
    if not get_settings().openai_api_key.strip():
        logger.info("[VLM auto] OPENAI_API_KEY 없음, 자동 보강 스킵")
        return None
    logger.info("[VLM auto] 저장 직후 보강 시작 report_id={}", report_id)
    return enrich_sr_report_images_vlm(report_id)
