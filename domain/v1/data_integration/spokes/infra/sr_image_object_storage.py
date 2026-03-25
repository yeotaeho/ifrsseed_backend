"""SR 추출 이미지 바이트 → S3/MinIO 업로드 (SR_IMAGE_STORAGE=s3).

환경 변수:
  AWS_S3_BUCKET 또는 SR_S3_BUCKET (필수)
  SR_S3_PREFIX (선택, 기본 sr-images/)
  AWS_REGION (선택)
  S3_ENDPOINT_URL (선택, MinIO 등)
  AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY (표준 boto3 자격)
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from loguru import logger

from backend.core.config.settings import get_settings


def mime_to_file_suffix(mime: str) -> str:
    m = (mime or "").lower().strip()
    return {
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/jpg": "jpg",
        "image/gif": "gif",
        "image/webp": "webp",
        "image/bmp": "bmp",
        "image/tiff": "tiff",
    }.get(m, "bin")


def get_s3_bucket_and_prefix() -> tuple[str, str]:
    s = get_settings()
    bucket = (s.sr_s3_bucket or "").strip()
    if not bucket:
        raise ValueError("SR_S3_BUCKET 또는 AWS_S3_BUCKET 이 필요합니다.")
    prefix = (s.sr_s3_prefix or "sr-images/").strip()
    if prefix and not prefix.endswith("/"):
        prefix += "/"
    return bucket, prefix


def upload_sr_image_bytes(
    *,
    key: str,
    body: bytes,
    content_type: str,
    bucket: Optional[str] = None,
) -> Dict[str, Any]:
    """
    boto3 로 단일 객체 업로드.

    Returns:
        {"bucket", "key", "etag"} (etag는 없을 수 있음)
    """
    try:
        import boto3  # type: ignore
    except ImportError as e:
        raise RuntimeError("boto3가 필요합니다. pip install boto3") from e

    s = get_settings()
    b = bucket or (s.sr_s3_bucket or "").strip()
    if not b:
        raise ValueError("bucket이 비어 있습니다.")

    endpoint = (s.s3_endpoint_url or "").strip() or None
    region = (s.aws_region or "ap-northeast-2").strip()

    client = boto3.client("s3", region_name=region, endpoint_url=endpoint)
    extra: Dict[str, Any] = {}
    if content_type:
        extra["ContentType"] = content_type

    resp = client.put_object(Bucket=b, Key=key, Body=body, **extra)
    etag = resp.get("ETag", "")
    if isinstance(etag, str):
        etag = etag.strip('"')
    logger.debug("[S3] put_object bucket={} key={} bytes={}", b, key, len(body))
    return {"bucket": b, "key": key, "etag": etag or None}


def download_sr_object_bytes(*, bucket: str, key: str) -> bytes:
    """S3/MinIO 객체 바이너리 다운로드 (VLM 보강 등)."""
    try:
        import boto3  # type: ignore
    except ImportError as e:
        raise RuntimeError("boto3가 필요합니다. pip install boto3") from e

    s = get_settings()
    endpoint = (s.s3_endpoint_url or "").strip() or None
    region = (s.aws_region or "ap-northeast-2").strip()
    client = boto3.client("s3", region_name=region, endpoint_url=endpoint)
    resp = client.get_object(Bucket=bucket, Key=key)
    body = resp["Body"].read()
    logger.debug("[S3] get_object bucket={} key={} bytes={}", bucket, key, len(body))
    return body


def build_rows_after_s3_upload(
    report_id: str,
    images_by_page: Dict[int, List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """
    extract_report_images_to_memory 결과(images_by_page)를 S3에 올린 뒤
    save_sr_report_images_batch용 행 리스트로 만듭니다.
    """
    bucket, prefix = get_s3_bucket_and_prefix()
    rows: List[Dict[str, Any]] = []

    max_b = os.getenv("SR_IMAGE_MAX_BLOB_BYTES", "").strip()
    max_bytes = int(max_b) if max_b.isdigit() else 0

    for page in sorted(images_by_page.keys()):
        for item in images_by_page[page]:
            raw = item.get("image_bytes") or b""
            if not raw:
                continue
            if max_bytes and len(raw) > max_bytes:
                logger.warning(
                    "[S3] 이미지 스킵 (크기 초과): page={} idx={} len={}",
                    page,
                    item.get("image_index"),
                    len(raw),
                )
                continue
            mime = item.get("mime_type") or "application/octet-stream"
            suf = mime_to_file_suffix(mime)
            idx = int(item.get("image_index", 0))
            key = f"{prefix}{report_id}/{page}_{idx}.{suf}"
            up = upload_sr_image_bytes(key=key, body=raw, content_type=mime, bucket=bucket)
            ed = {
                "storage": "s3",
                "bucket": up["bucket"],
                "key": up["key"],
                "etag": up.get("etag"),
                "mime_type": mime,
            }
            if item.get("size_bytes") is not None:
                ed["size_bytes"] = item["size_bytes"]
            rows.append(
                {
                    "page_number": int(page),
                    "image_index": idx,
                    "image_width": item.get("width"),
                    "image_height": item.get("height"),
                    "image_type": item.get("image_type"),
                    "caption_text": item.get("caption_text"),
                    "caption_confidence": item.get("caption_confidence"),
                    "extracted_data": ed,
                }
            )
    return rows
