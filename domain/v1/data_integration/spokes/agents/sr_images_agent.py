"""SRImagesAgent - 이미지 전용 에이전트 (결정적 파이프라인).

LLM 없이: get_pdf_metadata → extract_report_images → map_extracted_images_to_sr_report_rows
→ save_sr_report_images_batch
"""
from __future__ import annotations

import asyncio
import traceback
from typing import Any, Dict, List, Optional

from loguru import logger

from backend.core.config.settings import get_settings
from backend.domain.shared.tool.parsing.image_extractor import (
    extract_report_images,
    extract_report_images_to_memory,
)
from backend.domain.shared.tool.sr_report.images import map_extracted_images_to_sr_report_rows
from backend.domain.shared.tool.sr_report.index.sr_index_agent_tools import get_pdf_metadata
from backend.domain.shared.tool.sr_report.save.sr_save_tools import save_sr_report_images_batch


def _image_storage_mode() -> str:
    """SR_IMAGE_STORAGE: disk | memory | s3 (미설정 시 memory — 디스크 출력 경로 없이 메타만 DB)."""
    v = get_settings().sr_image_storage.strip().lower()
    if v in ("memory", "s3", "disk"):
        return v
    return "disk"


def _resolve_image_output_dir(explicit: Optional[str]) -> Optional[str]:
    if explicit and str(explicit).strip():
        return str(explicit).strip()
    env = get_settings().sr_image_output_dir.strip()
    return env or None


class SRImagesAgent:
    """SR 이미지 추출·저장. PyMuPDF 임베디드 이미지 → (선택) 디스크 / 메모리 / S3 + sr_report_images."""

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        if _args or _kwargs:
            logger.debug(
                "[SRImagesAgent] 미사용 인자 무시 args={} kwargs={}",
                _args,
                list(_kwargs.keys()),
            )

    async def execute(
        self,
        pdf_bytes: bytes,
        report_id: str,
        index_page_numbers: Optional[List[int]] = None,
        image_output_dir: Optional[str] = None,
        base_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        PDF에서 임베디드 이미지를 추출해 DB 메타(`sr_report_images`)를 적재합니다.

        저장 모드 (`SR_IMAGE_STORAGE`):
          - disk: 로컬 `image_output_dir` 또는 `SR_IMAGE_OUTPUT_DIR` 아래에 파일 저장.
          - memory: 메모리 추출 후 DB 저장. 기본적으로 `image_blob`(BYTEA)에도 픽셀 저장(SR_IMAGE_PERSIST_BLOB=0 으로 끔 가능, VLM 보강용).
          - s3: 메모리 추출 후 S3 업로드, 키·etag는 `extracted_data` (boto3, 버킷 env 필수).

        Args:
            pdf_bytes: PDF 바이너리
            report_id: historical_sr_reports.id
            index_page_numbers: 워크플로에서 넘기면 메타 조회 결과보다 우선하지 않음(메타 우선)
            image_output_dir: disk 모드에서 저장 루트. memory/s3 에서는 선택.
            base_name: 예약(파일명은 report_id 하위 폴더 규칙 사용).
        """
        _ = base_name
        errors: List[Dict[str, Any]] = []
        mode = _image_storage_mode()
        out_dir = _resolve_image_output_dir(image_output_dir)

        if mode == "disk" and not out_dir:
            logger.warning(
                "[SRImagesAgent] disk 모드인데 저장 경로 없음: image_output_dir={!r}, SR_IMAGE_OUTPUT_DIR 설정={}",
                image_output_dir,
                bool(get_settings().sr_image_output_dir.strip()),
            )
            return {
                "success": False,
                "message": "SR_IMAGE_STORAGE=disk 일 때 image_output_dir 또는 SR_IMAGE_OUTPUT_DIR 이 필요합니다.",
                "saved_count": 0,
                "sr_report_images": [],
                "errors": [{"stage": "config", "error": "missing image output directory"}],
            }

        if mode == "s3":
            try:
                from backend.domain.v1.data_integration.spokes.infra.sr_image_object_storage import (
                    get_s3_bucket_and_prefix,
                )

                get_s3_bucket_and_prefix()
            except ValueError as e:
                return {
                    "success": False,
                    "message": f"S3 설정 오류: {e}",
                    "saved_count": 0,
                    "sr_report_images": [],
                    "errors": [{"stage": "config", "error": str(e)}],
                }

        logger.info(
            "[SRImagesAgent] execute: report_id={} storage={} out_dir={} (API에서 지정={})",
            report_id,
            mode,
            out_dir or "(none)",
            bool(image_output_dir and str(image_output_dir).strip()),
        )

        try:
            meta = await asyncio.to_thread(get_pdf_metadata, report_id)
        except Exception as e:
            tb = traceback.format_exc()
            logger.exception("[SRImagesAgent] get_pdf_metadata 실패")
            return {
                "success": False,
                "message": f"메타데이터 조회 실패: {e}",
                "saved_count": 0,
                "sr_report_images": [],
                "errors": [{"stage": "get_pdf_metadata", "error": str(e), "traceback": tb}],
            }

        if isinstance(meta, dict) and meta.get("error"):
            err = str(meta["error"])
            return {
                "success": False,
                "message": f"메타데이터 오류: {err}",
                "saved_count": 0,
                "sr_report_images": [],
                "errors": [{"stage": "get_pdf_metadata", "error": err}],
            }

        total_pages = meta.get("total_pages")
        try:
            total_pages = int(total_pages) if total_pages is not None else 0
        except (TypeError, ValueError):
            total_pages = 0

        if total_pages <= 0:
            return {
                "success": False,
                "message": "total_pages가 유효하지 않습니다.",
                "saved_count": 0,
                "sr_report_images": [],
                "errors": [{"stage": "get_pdf_metadata", "error": "invalid total_pages"}],
            }

        idx_meta = meta.get("index_page_numbers")
        if idx_meta is not None:
            resolved_index: List[int] = [int(x) for x in idx_meta]
        elif index_page_numbers:
            resolved_index = [int(x) for x in index_page_numbers]
        else:
            resolved_index = []

        pages = list(range(1, total_pages + 1))

        def _extract_disk() -> Dict[str, Any]:
            return extract_report_images(
                pdf_bytes,
                pages,
                out_dir or "",
                report_id,
                index_page_numbers=resolved_index,
            )

        def _extract_memory() -> Dict[str, Any]:
            return extract_report_images_to_memory(
                pdf_bytes,
                pages,
                report_id,
                index_page_numbers=resolved_index,
            )

        stage = "extract_report_images" if mode == "disk" else "extract_report_images_to_memory"
        try:
            if mode == "disk":
                ex = await asyncio.to_thread(_extract_disk)
            else:
                ex = await asyncio.to_thread(_extract_memory)
        except Exception as e:
            tb = traceback.format_exc()
            logger.exception("[SRImagesAgent] 이미지 추출 실패 mode={}", mode)
            return {
                "success": False,
                "message": f"이미지 추출 실패: {e}",
                "saved_count": 0,
                "sr_report_images": [],
                "errors": [{"stage": stage, "error": str(e), "traceback": tb}],
            }

        if not ex.get("success"):
            err = ex.get("error") or "이미지 추출 실패"
            return {
                "success": False,
                "message": err,
                "saved_count": 0,
                "sr_report_images": [],
                "errors": [{"stage": stage, "error": err}],
            }

        images_by_page = ex.get("images_by_page") or {}
        if mode == "s3":
            from backend.domain.v1.data_integration.spokes.infra.sr_image_object_storage import (
                build_rows_after_s3_upload,
            )

            try:
                rows = await asyncio.to_thread(build_rows_after_s3_upload, report_id, images_by_page)
            except Exception as e:
                tb = traceback.format_exc()
                logger.exception("[SRImagesAgent] S3 업로드/행 구성 실패")
                return {
                    "success": False,
                    "message": f"S3 업로드 실패: {e}",
                    "saved_count": 0,
                    "sr_report_images": [],
                    "errors": [{"stage": "s3_upload", "error": str(e), "traceback": tb}],
                }
        else:
            rows = map_extracted_images_to_sr_report_rows(report_id, images_by_page)

        if not rows:
            logger.info("[SRImagesAgent] 추출된 이미지 없음 (필터 후 0건). DB 기존 이미지 삭제 후 0건 저장.")
            # replace_existing 로 기존 행 정리
            try:
                save_empty = await asyncio.to_thread(
                    save_sr_report_images_batch, report_id, [], replace_existing=True
                )
            except Exception as e:
                tb = traceback.format_exc()
                return {
                    "success": False,
                    "message": f"빈 배치 저장 실패: {e}",
                    "saved_count": 0,
                    "sr_report_images": [],
                    "errors": [{"stage": "save_sr_report_images_batch", "error": str(e), "traceback": tb}],
                }
            return {
                "success": True,
                "message": "추출된 임베디드 이미지 없음(0건). 기존 메타는 초기화됨.",
                "saved_count": int(save_empty.get("saved_count", 0)),
                "sr_report_images": [],
                "errors": None,
            }

        try:
            save_result = await asyncio.to_thread(
                save_sr_report_images_batch, report_id, rows, replace_existing=True
            )
        except Exception as e:
            tb = traceback.format_exc()
            logger.exception("[SRImagesAgent] save_sr_report_images_batch 실패")
            return {
                "success": False,
                "message": f"DB 저장 실패: {e}",
                "saved_count": 0,
                "sr_report_images": [],
                "errors": [{"stage": "save_sr_report_images_batch", "error": str(e), "traceback": tb}],
            }

        saved_count = int(save_result.get("saved_count", 0))
        per_errs = save_result.get("errors") or []
        if per_errs:
            for e in per_errs:
                if isinstance(e, dict):
                    errors.append({"stage": "save_sr_report_images_batch", **e})
                else:
                    errors.append({"stage": "save_sr_report_images_batch", "error": str(e)})

        saved_rows = save_result.get("saved_rows") or []
        msg = f"이미지 {saved_count}건 저장 완료 (PyMuPDF, storage={mode})"
        if saved_count <= 0:
            logger.warning(
                "[SRImagesAgent] success=False (saved_count=0): rows_in={} per_row_errors={} aggregate_errors={} message={}",
                len(rows),
                per_errs,
                errors if errors else None,
                msg,
            )
        return {
            "success": saved_count > 0,
            "message": msg,
            "saved_count": saved_count,
            "sr_report_images": saved_rows,
            "errors": errors if errors else None,
        }
