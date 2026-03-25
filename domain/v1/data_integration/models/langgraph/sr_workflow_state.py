"""LangGraph SR 워크플로우 상태 정의

노드 간에 전달되는 공유 상태. 모든 상태 전달은 이 TypedDict를 통해 이루어짐.
- fetch_and_parse → save_metadata → save_index → save_body → save_images
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class SRWorkflowState(TypedDict, total=False):
    """SR 보고서 워크플로우 공유 상태 (노드 간 상태 전달용)"""

    # ----- 입력 (오케스트레이터/API에서 주입) -----
    company: str
    year: int
    company_id: Optional[str]
    save_to_db: bool
    # 단계별 API용: "metadata" | "index" | "body" | "images" 이면 해당 노드만 실행 후 END
    only_step: Optional[str]

    # ----- fetch_and_parse 노드 입출력 -----
    success: bool
    message: str
    pdf_bytes: Optional[bytes]

    # ----- save_metadata 노드 출력 (다음 노드로 전달) -----
    report_id: Optional[str]
    index_page_numbers: Optional[List[int]]
    historical_sr_reports: Optional[Dict[str, Any]]

    # ----- save_index / save_body / save_images 노드 출력 -----
    index_saved_count: int
    body_saved_count: int
    images_saved_count: int
    sr_report_index: Optional[List[Dict[str, Any]]]  # save_index 노드에서 반환 (API 응답용)

    # ----- save_body 노드: SRBodyAgent 진단 (API extract-and-save/body 노출용) -----
    body_agent_message: Optional[str]
    body_agent_success: Optional[bool]
    body_agent_errors: Optional[List[Dict[str, Any]]]
    sr_report_body_db_row_count: Optional[int]

    # ----- save_images: 출력 디렉터리(API/LangGraph 주입) 및 SRImagesAgent 진단 -----
    image_output_dir: Optional[str]
    image_base_name: Optional[str]
    images_agent_message: Optional[str]
    images_agent_success: Optional[bool]
    images_agent_errors: Optional[List[Dict[str, Any]]]
    sr_report_images_db_row_count: Optional[int]
    # save_images 직후 자동 VLM 보강 (maybe_auto_enrich_after_image_save)
    images_vlm_auto_success: Optional[bool]
    images_vlm_auto_message: Optional[str]
    images_vlm_auto_updated: Optional[int]
    images_vlm_auto_skipped: Optional[int]

    # ----- parse_only 노드 출력 (DB 저장 없이 확인용) -----
    parsing_result: Optional[Dict[str, Any]]
