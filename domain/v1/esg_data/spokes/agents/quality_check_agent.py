"""UCM quality check agent (Phase 3)."""

from __future__ import annotations

from typing import List

from backend.domain.v1.esg_data.spokes.infra.ucm_pipeline_contracts import (
    UCMQualityIssue,
    UCMWorkflowCreateResult,
    UCMWorkflowQualityResult,
    UCMWorkflowValidationResult,
)


class QualityCheckAgent:
    """워크플로우 결과를 후처리해 품질 요약을 만든다."""

    def summarize(
        self,
        *,
        create_result: UCMWorkflowCreateResult | None = None,
        validation_result: UCMWorkflowValidationResult | None = None,
    ) -> UCMWorkflowQualityResult:
        issues: List[UCMQualityIssue] = []

        if create_result and create_result.get("status") == "error":
            issues.append(
                {"type": "create_error", "message": str(create_result.get("message", ""))}
            )
        if validation_result and validation_result.get("status") == "error":
            issues.append(
                {"type": "validation_error", "message": str(validation_result.get("message", ""))}
            )

        if validation_result and validation_result.get("status") == "success":
            metrics = validation_result.get("metrics", {})
            missing = int(metrics.get("missing_dp_references_in_ucm", 0) or 0)
            if missing > 0:
                issues.append(
                    {
                        "type": "missing_dp_references",
                        "count": missing,
                        "message": "일부 UCM이 존재하지 않는 data_point를 참조합니다.",
                    }
                )

        return {
            "status": "success",
            "issues_count": len(issues),
            "issues": issues,
        }
