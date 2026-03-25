from backend.domain.v1.esg_data.hub.orchestrator.ucm_orchestrator import UCMOrchestrator


class _StubAgent:
    def __init__(self) -> None:
        self.called = []

    def create_mappings(self, **kwargs):
        self.called.append(("create", kwargs))
        return {"status": "success", "mode": "dry_run"}

    def suggest_mappings(self, **kwargs):
        self.called.append(("suggest", kwargs))
        return {"status": "success", "count": 1, "items": [{}]}


class _StubMappingService:
    def __init__(self) -> None:
        self.called = []

    def validate_mappings(self):
        self.called.append("validate")
        return {"status": "success", "metrics": {"issues": 0}}


def test_orchestrator_delegates_create_and_suggest_to_agent() -> None:
    agent = _StubAgent()
    svc = _StubMappingService()
    orchestrator = UCMOrchestrator(creation_agent=agent, mapping_service=svc)

    create_res = orchestrator.create_mappings("GRI", "ESRS", dry_run=True)
    suggest_res = orchestrator.suggest_mappings("GRI", "ESRS", limit=5)

    assert create_res["status"] == "success"
    assert suggest_res["status"] == "success"
    assert agent.called[0][0] == "create"
    assert agent.called[1][0] == "suggest"


def test_orchestrator_delegates_validation_to_service() -> None:
    agent = _StubAgent()
    svc = _StubMappingService()
    orchestrator = UCMOrchestrator(creation_agent=agent, mapping_service=svc)

    health = orchestrator.validate_mapping_health()

    assert health["status"] == "success"
    assert svc.called == ["validate"]
