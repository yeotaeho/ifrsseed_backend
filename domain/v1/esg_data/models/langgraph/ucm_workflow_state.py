"""UCM workflow 그래프 상태 (Phase 3). 필드 타입은 ``spokes.infra.ucm_pipeline_contracts`` 와 정렬."""

from __future__ import annotations

from typing import List, Literal, TypedDict

from backend.domain.v1.esg_data.spokes.infra.ucm_pipeline_contracts import (
    UCMQualityIssue,
    UCMWorkflowCreateResult,
    UCMWorkflowQualityResult,
    UCMWorkflowValidationResult,
)


class UCMWorkflowState(TypedDict, total=False):
    # 입력
    source_standard: str
    target_standard: str
    vector_threshold: float
    structural_threshold: float
    final_threshold: float
    batch_size: int
    dry_run: bool
    run_quality_check: bool
    force_validate_only: bool

    # 중간/출력
    route: Literal["creation_agent", "validation_agent"]
    create_result: UCMWorkflowCreateResult
    validation_result: UCMWorkflowValidationResult
    quality_result: UCMWorkflowQualityResult
    issues: List[UCMQualityIssue]
    success: bool
    message: str
