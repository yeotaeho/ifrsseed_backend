from backend.domain.v1.esg_data.hub.orchestrator.ucm_orchestrator import UCMOrchestrator
from backend.domain.v1.esg_data.hub.routing.agent_router import AgentRouter


class _StubCreationAgent:
    def create_mappings(self, **_kwargs):
        return {"status": "success", "stats": {"processed": 1}}


class _StubValidationAgent:
    def validate(self):
        return {
            "status": "success",
            "metrics": {"missing_dp_references_in_ucm": 0},
        }


class _StubQualityAgent:
    def __init__(self) -> None:
        self.called = 0

    def summarize(self, **_kwargs):
        self.called += 1
        return {"status": "success", "issues_count": 0, "issues": []}


def test_agent_router_routes_to_validation() -> None:
    router = AgentRouter()
    routed = router.route({"route": "validation_agent"})
    assert routed == "validation_agent"


def test_phase3_workflow_fallback_success() -> None:
    quality = _StubQualityAgent()
    orchestrator = UCMOrchestrator(
        creation_agent=_StubCreationAgent(),  # type: ignore[arg-type]
        validation_agent=_StubValidationAgent(),  # type: ignore[arg-type]
        quality_check_agent=quality,  # type: ignore[arg-type]
    )
    result = orchestrator.run_ucm_workflow(
        source_standard="GRI",
        target_standard="ESRS",
        dry_run=True,
        run_quality_check=True,
    )

    assert result["status"] == "success"
    assert "create_result" in result
    assert "validation_result" in result
    assert "quality_result" in result
    assert "workflow" in result
    assert "langgraph" in result["workflow"]
    assert quality.called == 0  # missing=0이면 quality 단계 자동 생략


def test_phase3_workflow_force_validate_only() -> None:
    quality = _StubQualityAgent()
    orchestrator = UCMOrchestrator(
        creation_agent=_StubCreationAgent(),  # type: ignore[arg-type]
        validation_agent=_StubValidationAgent(),  # type: ignore[arg-type]
        quality_check_agent=quality,  # type: ignore[arg-type]
    )
    result = orchestrator.run_ucm_workflow(
        source_standard="GRI",
        target_standard="ESRS",
        force_validate_only=True,
    )
    assert result["workflow"]["routed_to"] == "validation_agent"
    assert result.get("create_result") is None
