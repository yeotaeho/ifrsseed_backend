"""UCM validation agent (Phase 3)."""

from __future__ import annotations

from backend.domain.v1.esg_data.hub.repositories import UCMRepository
from backend.domain.v1.esg_data.spokes.infra.ucm_mapping_service import UCMMappingService
from backend.domain.v1.esg_data.spokes.infra.ucm_pipeline_contracts import UCMWorkflowValidationResult


class ValidationAgent:
    """UCM 정합성 점검."""

    def __init__(
        self,
        mapping_service: UCMMappingService | None = None,
        repository: UCMRepository | None = None,
    ) -> None:
        # Backward compatibility: if mapping_service is injected, keep using it.
        self.mapping_service = mapping_service
        self.repository = repository or UCMRepository()

    def validate(self) -> UCMWorkflowValidationResult:
        if self.mapping_service is not None:
            return self.mapping_service.validate_mappings()
        return self.repository.validate_mappings()
