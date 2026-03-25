"""PDF에서 임베디드 이미지 추출 (PyMuPDF).

SR_IMAGES_PARSING_DESIGN Phase 1: xref 기반 추출, 썸네일·아이콘 휴리스틱 필터.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from loguru import logger

from backend.domain.shared.tool.parsing.common import PYMUPDF_AVAILABLE, open_pdf


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name, "").strip().lower()
    if v in ("0", "false", "no", "off"):
        return False
    if v in ("1", "true", "yes", "on"):
        return True
    return default


def _min_edge() -> int:
    try:
        return max(8, int(os.getenv("SR_IMAGE_MIN_EDGE", "32")))
    except ValueError:
        return 32


def _min_bytes() -> int:
    try:
        return max(0, int(os.getenv("SR_IMAGE_MIN_BYTES", "200")))
    except ValueError:
        return 200


def _max_edge_limit() -> int:
    """긴 변 기준 이 값을 넘으면 축소(0 또는 미설정 = 비활성)."""
    try:
        v = int(os.getenv("SR_IMAGE_MAX_EDGE", "0").strip() or "0")
        return max(0, v)
    except ValueError:
        return 0


def _maybe_downscale_image(
    raw: bytes,
    width: int,
    height: int,
    ext: str,
    max_edge: int,
) -> tuple[bytes, str, int, int]:
    """
    PyMuPDF Pixmap으로 디코드 후 긴 변이 max_edge를 넘으면 비율 유지 축소, PNG로 저장.
    실패 시 원본 반환.
    """
    if max_edge <= 0 or width <= 0 or height <= 0 or not raw:
        return raw, ext, width, height
    m = max(width, height)
    if m <= max_edge:
        return raw, ext, width, height
    if not PYMUPDF_AVAILABLE:
        return raw, ext, width, height
    import fitz

    try:
        src = fitz.Pixmap(raw)
    except Exception:
        return raw, ext, width, height
    try:
        scale = max_edge / m
        nw = max(1, int(width * scale))
        nh = max(1, int(height * scale))
        scaled = fitz.Pixmap(src, nw, nh)
        out = scaled.tobytes("png")
        return out, "png", scaled.width, scaled.height
    except Exception as e:
        logger.debug("[image_extractor] downscale 실패, 원본 유지: {}", e)
        return raw, ext, width, height


def extract_report_images(
    pdf_bytes: bytes,
    pages: List[int],
    output_dir: str,
    report_id: str,
    *,
    index_page_numbers: Optional[List[int]] = None,
    skip_index_pages: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    지정 페이지에서 임베디드 래스터 이미지를 파일로 저장하고 메타를 반환합니다.

    Args:
        pdf_bytes: PDF 바이너리
        pages: 처리할 1-based 페이지 번호 목록
        output_dir: 이미지 저장 루트 디렉터리
        report_id: 보고서 UUID (하위 폴더명에 사용)
        index_page_numbers: 인덱스 페이지 (skip 시 제외)
        skip_index_pages: None이면 환경변수 SR_IMAGE_SKIP_INDEX_PAGES (기본 True)

    Returns:
        {
            "success": bool,
            "images_by_page": { page_number: [ { "path", "width", "height", "size_bytes", "image_index" }, ... ] },
            "error": str | None,
            "skipped_pages": [int],  # 인덱스 등으로 스킵된 페이지
        }
    """
    if not PYMUPDF_AVAILABLE:
        return {
            "success": False,
            "images_by_page": {},
            "error": "PyMuPDF(pymupdf) 미설치",
            "skipped_pages": [],
        }

    if skip_index_pages is None:
        skip_index_pages = _env_bool("SR_IMAGE_SKIP_INDEX_PAGES", True)

    index_set: Set[int] = set()
    for x in index_page_numbers or []:
        try:
            index_set.add(int(x))
        except (TypeError, ValueError):
            continue

    out_dir = Path(output_dir)
    try:
        rid = uuid.UUID(str(report_id))
    except (ValueError, TypeError):
        return {
            "success": False,
            "images_by_page": {},
            "error": f"유효하지 않은 report_id: {report_id!r}",
            "skipped_pages": [],
        }

    sub = out_dir / str(rid)
    try:
        sub.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return {
            "success": False,
            "images_by_page": {},
            "error": f"출력 디렉터리 생성 실패: {e}",
            "skipped_pages": [],
        }

    min_edge = _min_edge()
    min_image_bytes = _min_bytes()
    max_edge = _max_edge_limit()
    images_by_page: Dict[int, List[Dict[str, Any]]] = {}
    skipped_pages: List[int] = []

    try:
        doc = open_pdf(pdf_bytes)
    except Exception as e:
        logger.exception("[image_extractor] PDF 열기 실패")
        return {
            "success": False,
            "images_by_page": {},
            "error": str(e),
            "skipped_pages": [],
        }

    try:
        for pn in pages:
            try:
                pno = int(pn)
            except (TypeError, ValueError):
                continue
            if pno < 1 or pno > doc.page_count:
                continue
            if skip_index_pages and pno in index_set:
                skipped_pages.append(pno)
                continue

            page = doc.load_page(pno - 1)
            imglist = page.get_images(full=True)
            seen_xref: Set[int] = set()
            page_entries: List[Dict[str, Any]] = []
            local_idx = 0

            for img in imglist:
                xref = img[0]
                if xref in seen_xref:
                    continue
                seen_xref.add(xref)

                try:
                    info = doc.extract_image(xref)
                except Exception as e:
                    logger.debug("[image_extractor] extract_image xref={} page={} err={}", xref, pno, e)
                    continue

                raw = info.get("image") or b""
                w = int(info.get("width") or 0)
                h = int(info.get("height") or 0)
                ext = (info.get("ext") or "png").lower()
                if ext not in ("png", "jpeg", "jpg", "jpx", "jp2", "gif", "bmp", "tiff", "webp"):
                    ext = "png"

                raw, ext, w, h = _maybe_downscale_image(raw, w, h, ext, max_edge)

                if len(raw) < min_image_bytes:
                    continue
                if w > 0 and h > 0 and (w < min_edge or h < min_edge):
                    continue

                fname = f"{pno}_{local_idx}.{ext}"
                fpath = sub / fname
                try:
                    fpath.write_bytes(raw)
                except OSError as e:
                    logger.warning("[image_extractor] 파일 쓰기 실패 {}: {}", fpath, e)
                    continue

                size_bytes = fpath.stat().st_size
                page_entries.append({
                    "path": str(fpath.resolve()),
                    "width": w or None,
                    "height": h or None,
                    "size_bytes": size_bytes,
                    "image_index": local_idx,
                })
                local_idx += 1

            if page_entries:
                images_by_page[pno] = page_entries
    finally:
        doc.close()

    if _env_bool("SR_IMAGE_DEBUG", False):
        total = sum(len(v) for v in images_by_page.values())
        logger.info(
            "[SR_IMAGE] 추출 완료 | pages_with_images={} total_images={} skipped_index_pages={}",
            len(images_by_page),
            total,
            len(skipped_pages),
        )

    return {
        "success": True,
        "images_by_page": images_by_page,
        "error": None,
        "skipped_pages": skipped_pages,
    }


def _mime_from_ext(ext: str) -> str:
    e = (ext or "").lower().lstrip(".")
    return {
        "png": "image/png",
        "jpeg": "image/jpeg",
        "jpg": "image/jpeg",
        "jpx": "image/jpx",
        "jp2": "image/jp2",
        "gif": "image/gif",
        "bmp": "image/bmp",
        "tiff": "image/tiff",
        "webp": "image/webp",
    }.get(e, "application/octet-stream")


def extract_report_images_to_memory(
    pdf_bytes: bytes,
    pages: List[int],
    report_id: str,
    *,
    index_page_numbers: Optional[List[int]] = None,
    skip_index_pages: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    extract_report_images 와 동일 필터·휴리스틱이나 디스크에 쓰지 않고
    각 항목에 image_bytes·mime_type 를 담아 반환합니다.

    Returns:
        success, images_by_page (항목에 path 없음), error, skipped_pages
    """
    if not PYMUPDF_AVAILABLE:
        return {
            "success": False,
            "images_by_page": {},
            "error": "PyMuPDF(pymupdf) 미설치",
            "skipped_pages": [],
        }

    if skip_index_pages is None:
        skip_index_pages = _env_bool("SR_IMAGE_SKIP_INDEX_PAGES", True)

    index_set: Set[int] = set()
    for x in index_page_numbers or []:
        try:
            index_set.add(int(x))
        except (TypeError, ValueError):
            continue

    try:
        uuid.UUID(str(report_id))
    except (ValueError, TypeError):
        return {
            "success": False,
            "images_by_page": {},
            "error": f"유효하지 않은 report_id: {report_id!r}",
            "skipped_pages": [],
        }

    min_edge = _min_edge()
    min_image_bytes = _min_bytes()
    max_edge = _max_edge_limit()
    images_by_page: Dict[int, List[Dict[str, Any]]] = {}
    skipped_pages: List[int] = []

    try:
        doc = open_pdf(pdf_bytes)
    except Exception as e:
        logger.exception("[image_extractor] PDF 열기 실패")
        return {
            "success": False,
            "images_by_page": {},
            "error": str(e),
            "skipped_pages": [],
        }

    try:
        for pn in pages:
            try:
                pno = int(pn)
            except (TypeError, ValueError):
                continue
            if pno < 1 or pno > doc.page_count:
                continue
            if skip_index_pages and pno in index_set:
                skipped_pages.append(pno)
                continue

            page = doc.load_page(pno - 1)
            imglist = page.get_images(full=True)
            seen_xref: Set[int] = set()
            page_entries: List[Dict[str, Any]] = []
            local_idx = 0

            for img in imglist:
                xref = img[0]
                if xref in seen_xref:
                    continue
                seen_xref.add(xref)

                try:
                    info = doc.extract_image(xref)
                except Exception as e:
                    logger.debug("[image_extractor] extract_image xref={} page={} err={}", xref, pno, e)
                    continue

                raw = info.get("image") or b""
                w = int(info.get("width") or 0)
                h = int(info.get("height") or 0)
                ext = (info.get("ext") or "png").lower()
                if ext not in ("png", "jpeg", "jpg", "jpx", "jp2", "gif", "bmp", "tiff", "webp"):
                    ext = "png"

                raw, ext, w, h = _maybe_downscale_image(raw, w, h, ext, max_edge)

                if len(raw) < min_image_bytes:
                    continue
                if w > 0 and h > 0 and (w < min_edge or h < min_edge):
                    continue

                mime = _mime_from_ext(ext)
                page_entries.append({
                    "image_bytes": raw,
                    "mime_type": mime,
                    "width": w or None,
                    "height": h or None,
                    "size_bytes": len(raw),
                    "image_index": local_idx,
                })
                local_idx += 1

            if page_entries:
                images_by_page[pno] = page_entries
    finally:
        doc.close()

    if _env_bool("SR_IMAGE_DEBUG", False):
        total = sum(len(v) for v in images_by_page.values())
        logger.info(
            "[SR_IMAGE] 메모리 추출 완료 | pages_with_images={} total_images={} skipped_index_pages={}",
            len(images_by_page),
            total,
            len(skipped_pages),
        )

    return {
        "success": True,
        "images_by_page": images_by_page,
        "error": None,
        "skipped_pages": skipped_pages,
    }
