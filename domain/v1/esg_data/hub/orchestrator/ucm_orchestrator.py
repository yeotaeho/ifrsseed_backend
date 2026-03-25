"""ESG Data — UCM orchestrator (legacy batch + policy pipeline + LangGraph workflow)."""

from __future__ import annotations

from typing import Any, Dict, List

from backend.domain.v1.esg_data.spokes.agents.ucm_creation_agent import UCMCreationAgent
from backend.domain.v1.esg_data.spokes.agents import ucm_policy
from backend.domain.v1.esg_data.spokes.agents.quality_check_agent import QualityCheckAgent
from backend.domain.v1.esg_data.spokes.agents.validation_agent import ValidationAgent
from backend.domain.v1.esg_data.hub.repositories import UCMRepository
from backend.domain.v1.esg_data.hub.routing.agent_router import AgentRouter
from backend.domain.v1.esg_data.models.langgraph import UCMWorkflowState
from backend.domain.v1.esg_data.models.bases import DataPoint
from backend.domain.v1.esg_data.spokes.infra.ucm_mapping_service import UCMMappingService
from backend.domain.shared.tool.UnifiedColumnMapping import (
    EmbeddingCandidateTool,
    RuleValidationTool,
    SchemaMappingTool,
)
from backend.core.db import get_session

try:
    from langgraph.graph import END, StateGraph

    LANGGRAPH_AVAILABLE = True
except ImportError:
    END = None
    StateGraph = None
    LANGGRAPH_AVAILABLE = False


def _primary_rulebook_id_for_dp(db: Any, source_dp_id: str) -> str | None:
    from backend.domain.v1.esg_data.models.bases import Rulebook

    rb = (
        db.query(Rulebook)
        .filter(Rulebook.is_active.is_(True), Rulebook.primary_dp_id == source_dp_id)
        .first()
    )
    if rb and len(rb.rulebook_id) <= 50:
        return rb.rulebook_id
    return None


class UCMOrchestrator:
    """Coordinates UCM flows: legacy equivalent_dps batch, policy pipeline, Phase-3 workflow."""

    def __init__(
        self,
        creation_agent: UCMCreationAgent | None = None,
        validation_agent: ValidationAgent | None = None,
        quality_check_agent: QualityCheckAgent | None = None,
        router: AgentRouter | None = None,
        mapping_service: UCMMappingService | None = None,
        repository: UCMRepository | None = None,
    ) -> None:
        self.repository = repository or UCMRepository()
        self.mapping_service = mapping_service or UCMMappingService(self.repository)
        self.creation_agent = creation_agent or UCMCreationAgent(self.mapping_service)
        self.validation_agent = validation_agent or ValidationAgent(repository=self.repository)
        self.quality_check_agent = quality_check_agent or QualityCheckAgent()
        self.router = router or AgentRouter()

    def create_mappings(
        self,
        source_standard: str,
        target_standard: str,
        vector_threshold: float = 0.70,
        structural_threshold: float = 0.50,
        final_threshold: float = 0.75,
        batch_size: int = 40,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Run legacy batch mapping (equivalent_dps)."""
        return self.creation_agent.create_mappings(
            source_standard=source_standard,
            target_standard=target_standard,
            vector_threshold=vector_threshold,
            structural_threshold=structural_threshold,
            final_threshold=final_threshold,
            batch_size=batch_size,
            dry_run=dry_run,
        )

    def suggest_mappings(
        self,
        source_standard: str,
        target_standard: str,
        vector_threshold: float = 0.70,
        structural_threshold: float = 0.50,
        final_threshold: float = 0.75,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """Dry-run style suggestions."""
        return self.creation_agent.suggest_mappings(
            source_standard=source_standard,
            target_standard=target_standard,
            vector_threshold=vector_threshold,
            structural_threshold=structural_threshold,
            final_threshold=final_threshold,
            limit=limit,
        )

    def validate_mapping_health(self) -> Dict[str, Any]:
        """Return UCM vs data_points health metrics."""
        return self.mapping_service.validate_mappings()

    def run_ucm_policy_pipeline(
        self,
        source_standard: str,
        target_standard: str,
        *,
        batch_size: int = 40,
        dry_run: bool = True,
        top_k: int = 5,
        vector_threshold: float = 0.70,
        structural_threshold: float = 0.50,
        final_threshold: float = 0.75,
        use_llm_in_mapping_service: bool = False,
        llm_model: str = "gpt-5-mini",
    ) -> Dict[str, Any]:
        """§2 pipeline: embedding -> rule validation -> (optional) LLM -> policy -> payload -> upsert."""
        embedding_tool = EmbeddingCandidateTool()
        rule_tool = RuleValidationTool()
        schema_tool = SchemaMappingTool()

        stats: Dict[str, int] = {
            "processed": 0,
            "accept": 0,
            "review": 0,
            "reject": 0,
            "upsert_ok": 0,
            "upsert_error": 0,
            "errors": 0,
        }
        items: List[Dict[str, Any]] = []
        db = None
        try:
            db = get_session()
            source_rows = (
                db.query(DataPoint)
                .filter(
                    DataPoint.standard == source_standard,
                    DataPoint.is_active.is_(True),
                )
                .limit(batch_size)
                .all()
            )

            for source in source_rows:
                stats["processed"] += 1
                src_id = source.dp_id

                emb = embedding_tool.run(
                    db,
                    self.mapping_service,
                    source_dp_id=src_id,
                    target_standard=target_standard,
                    top_k=top_k,
                    vector_threshold=vector_threshold,
                    structural_threshold=structural_threshold,
                    final_threshold=final_threshold,
                )
                if emb["status"] != "success" or not emb["candidates"]:
                    stats["reject"] += 1
                    stats["errors"] += 1
                    items.append(
                        {
                            "source_dp_id": src_id,
                            "status": "error",
                            "message": emb.get("message", "no candidates"),
                        }
                    )
                    continue

                rv = rule_tool.run(
                    db,
                    self.mapping_service,
                    source_dp_id=src_id,
                    candidates=emb["candidates"],
                )
                if rv["status"] != "success" or not rv["per_candidate"]:
                    stats["reject"] += 1
                    stats["errors"] += 1
                    items.append(
                        {
                            "source_dp_id": src_id,
                            "status": "error",
                            "message": rv.get("message", "rule validation failed"),
                        }
                    )
                    continue

                best = self.creation_agent.policy_pick_best(emb["candidates"], rv["per_candidate"])
                if best is None:
                    decision = {"decision": "reject", "confidence": 0.0, "reason_codes": ["no_valid_pair"]}
                    stats["reject"] += 1
                    items.append({"source_dp_id": src_id, "decision": decision})
                    continue

                candidate, rule_row = best
                tentative = ucm_policy.tentative_decision_from_scores(
                    ucm_policy.compute_final_score(
                        float(candidate["hybrid_score"]),
                        float(rule_row["rule_score"]),
                        float(rule_row["structure_score"]),
                        float(rule_row["requirement_score"]),
                        ucm_policy.compute_penalty(rule_row["violations"]),
                    ),
                    any(v["severity"] == "critical" for v in rule_row["violations"]),
                )
                llm_result = None
                if use_llm_in_mapping_service and ucm_policy.should_call_llm(
                    float(candidate["hybrid_score"]),
                    bool(rule_row["rule_pass"]),
                    tentative,
                ):
                    llm_result = self.creation_agent.llm_refinement(
                        {
                            "source_dp_id": src_id,
                            "target_dp_id": candidate["target_dp_id"],
                            "candidate": candidate,
                            "rule_row": rule_row,
                            "tentative_decision": tentative,
                            "model": llm_model,
                        }
                    )

                decision = self.creation_agent.policy_finalize_decision(
                    source_dp_id=src_id,
                    candidate=candidate,
                    rule_row=rule_row,
                    llm_result=llm_result,
                    policy_version="ucm_pipeline_v1",
                )
                decision_label = decision["decision"]
                stats[decision_label] += 1

                target = (
                    db.query(DataPoint)
                    .filter(
                        DataPoint.dp_id == candidate["target_dp_id"],
                        DataPoint.is_active.is_(True),
                    )
                    .first()
                )
                if target is None:
                    stats["errors"] += 1
                    items.append(
                        {
                            "source_dp_id": src_id,
                            "decision": decision,
                            "status": "error",
                            "message": "target dp not found",
                        }
                    )
                    continue

                payload_result = schema_tool.build_payload(
                    source_dp=source,
                    target_dp=target,
                    decision=decision,
                    primary_rulebook_id=_primary_rulebook_id_for_dp(db, src_id),
                )

                upsert_result: Dict[str, Any] | None = None
                if payload_result["status"] == "success":
                    if dry_run:
                        upsert_result = {"status": "skipped", "message": "dry_run"}
                    else:
                        upsert_result = self.mapping_service.upsert_ucm_from_payload(payload_result["payload"])
                        if upsert_result.get("status") == "success":
                            stats["upsert_ok"] += 1
                        else:
                            stats["upsert_error"] += 1
                            stats["errors"] += 1
                else:
                    stats["errors"] += 1

                items.append(
                    {
                        "source_dp_id": src_id,
                        "target_dp_id": candidate["target_dp_id"],
                        "decision": decision,
                        "llm_model": llm_model if llm_result else None,
                        "llm_result": llm_result,
                        "payload_result": payload_result,
                        "upsert_result": upsert_result,
                    }
                )

            return {
                "status": "success",
                "pipeline": "ucm_policy_v1",
                "dry_run": dry_run,
                "source_standard": source_standard,
                "target_standard": target_standard,
                "stats": stats,
                "items": items,
            }
        except Exception as e:
            return {
                "status": "error",
                "message": str(e),
                "pipeline": "ucm_policy_v1",
                "dry_run": dry_run,
                "source_standard": source_standard,
                "target_standard": target_standard,
                "stats": stats,
                "items": items,
            }
        finally:
            if db is not None:
                db.close()

    def run_ucm_nearest_pipeline(
        self,
        *,
        batch_size: int = 40,
        dry_run: bool = True,
        top_k: int = 5,
        vector_threshold: float = 0.70,
        structural_threshold: float = 0.50,
        final_threshold: float = 0.75,
        use_llm_in_mapping_service: bool = False,
        llm_model: str = "gpt-5-mini",
    ) -> Dict[str, Any]:
        """기준서 입력 없이: 각 DP에 대해 다른 기준서 DP 최근접 후보로 §2 파이프라인 수행."""
        embedding_tool = EmbeddingCandidateTool()
        rule_tool = RuleValidationTool()
        schema_tool = SchemaMappingTool()

        stats: Dict[str, int] = {
            "processed": 0,
            "accept": 0,
            "review": 0,
            "reject": 0,
            "upsert_ok": 0,
            "upsert_error": 0,
            "errors": 0,
        }
        items: List[Dict[str, Any]] = []
        db = None
        try:
            db = get_session()
            sources = db.query(DataPoint).filter(DataPoint.is_active.is_(True)).limit(batch_size).all()
            for source in sources:
                stats["processed"] += 1
                src_id = source.dp_id

                emb = embedding_tool.run(
                    db,
                    self.mapping_service,
                    source_dp_id=src_id,
                    target_standard=None,
                    top_k=top_k,
                    vector_threshold=vector_threshold,
                    structural_threshold=structural_threshold,
                    final_threshold=final_threshold,
                )
                if emb["status"] != "success" or not emb["candidates"]:
                    stats["reject"] += 1
                    stats["errors"] += 1
                    items.append({"source_dp_id": src_id, "status": "error", "message": "no candidates"})
                    continue

                rv = rule_tool.run(
                    db,
                    self.mapping_service,
                    source_dp_id=src_id,
                    candidates=emb["candidates"],
                )
                if rv["status"] != "success" or not rv["per_candidate"]:
                    stats["reject"] += 1
                    stats["errors"] += 1
                    items.append({"source_dp_id": src_id, "status": "error", "message": rv.get("message")})
                    continue

                best = self.creation_agent.policy_pick_best(emb["candidates"], rv["per_candidate"])
                if best is None:
                    stats["reject"] += 1
                    items.append({"source_dp_id": src_id, "status": "error", "message": "no valid pair"})
                    continue

                candidate, rule_row = best
                tentative = ucm_policy.tentative_decision_from_scores(
                    ucm_policy.compute_final_score(
                        float(candidate["hybrid_score"]),
                        float(rule_row["rule_score"]),
                        float(rule_row["structure_score"]),
                        float(rule_row["requirement_score"]),
                        ucm_policy.compute_penalty(rule_row["violations"]),
                    ),
                    any(v["severity"] == "critical" for v in rule_row["violations"]),
                )
                llm_result = None
                if use_llm_in_mapping_service and ucm_policy.should_call_llm(
                    float(candidate["hybrid_score"]),
                    bool(rule_row["rule_pass"]),
                    tentative,
                ):
                    llm_result = self.creation_agent.llm_refinement(
                        {
                            "source_dp_id": src_id,
                            "target_dp_id": candidate["target_dp_id"],
                            "candidate": candidate,
                            "rule_row": rule_row,
                            "tentative_decision": tentative,
                            "model": llm_model,
                        }
                    )

                decision = self.creation_agent.policy_finalize_decision(
                    source_dp_id=src_id,
                    candidate=candidate,
                    rule_row=rule_row,
                    llm_result=llm_result,
                    policy_version="ucm_pipeline_v1",
                )
                stats[decision["decision"]] += 1

                target = (
                    db.query(DataPoint)
                    .filter(DataPoint.dp_id == candidate["target_dp_id"], DataPoint.is_active.is_(True))
                    .first()
                )
                if not target:
                    stats["errors"] += 1
                    items.append({"source_dp_id": src_id, "status": "error", "message": "target dp not found"})
                    continue

                payload_result = schema_tool.build_payload(
                    source_dp=source,
                    target_dp=target,
                    decision=decision,
                    primary_rulebook_id=_primary_rulebook_id_for_dp(db, src_id),
                )
                upsert_result: Dict[str, Any] | None = None
                if payload_result["status"] == "success":
                    if dry_run:
                        upsert_result = {"status": "skipped", "message": "dry_run"}
                    else:
                        upsert_result = self.mapping_service.upsert_ucm_from_payload(payload_result["payload"])
                        if upsert_result.get("status") == "success":
                            stats["upsert_ok"] += 1
                        else:
                            stats["upsert_error"] += 1
                            stats["errors"] += 1
                else:
                    stats["errors"] += 1

                items.append(
                    {
                        "source_dp_id": src_id,
                        "target_dp_id": candidate["target_dp_id"],
                        "source_standard": source.standard,
                        "target_standard": target.standard,
                        "decision": decision,
                        "llm_model": llm_model if llm_result else None,
                        "llm_result": llm_result,
                        "payload_result": payload_result,
                        "upsert_result": upsert_result,
                    }
                )

            return {
                "status": "success",
                "pipeline": "ucm_nearest_v1",
                "dry_run": dry_run,
                "stats": stats,
                "items": items,
            }
        except Exception as e:
            return {"status": "error", "pipeline": "ucm_nearest_v1", "message": str(e), "stats": stats, "items": items}
        finally:
            if db is not None:
                db.close()

    # ---------- Phase 3 ----------
    def run_ucm_workflow(
        self,
        source_standard: str,
        target_standard: str,
        vector_threshold: float = 0.70,
        structural_threshold: float = 0.50,
        final_threshold: float = 0.75,
        batch_size: int = 40,
        dry_run: bool = False,
        run_quality_check: bool = True,
        force_validate_only: bool = False,
    ) -> Dict[str, Any]:
        """Phase-3 workflow: legacy create → validate → optional quality."""
        initial: UCMWorkflowState = {
            "source_standard": source_standard,
            "target_standard": target_standard,
            "vector_threshold": vector_threshold,
            "structural_threshold": structural_threshold,
            "final_threshold": final_threshold,
            "batch_size": batch_size,
            "dry_run": dry_run,
            "run_quality_check": run_quality_check,
            "force_validate_only": force_validate_only,
            "route": "creation_agent",
            "issues": [],
            "success": False,
            "message": "",
        }
        if LANGGRAPH_AVAILABLE:
            return self._run_workflow_with_langgraph(initial)
        return self._run_workflow_fallback(initial)

    def _run_workflow_fallback(self, state: UCMWorkflowState) -> Dict[str, Any]:
        """Sequential workflow when LangGraph is not installed."""
        routed = self.router.route(state)
        if routed == "creation_agent":
            state["create_result"] = self.creation_agent.create_mappings(
                source_standard=state["source_standard"],
                target_standard=state["target_standard"],
                vector_threshold=state["vector_threshold"],
                structural_threshold=state["structural_threshold"],
                final_threshold=state["final_threshold"],
                batch_size=state["batch_size"],
                dry_run=state["dry_run"],
            )
            state["route"] = "validation_agent"

        state["validation_result"] = self.validation_agent.validate()
        if self._should_run_quality(state):
            state["quality_result"] = self.quality_check_agent.summarize(
                create_result=state.get("create_result"),
                validation_result=state.get("validation_result"),
            )
            state["issues"] = state["quality_result"].get("issues", [])
        state["success"] = (
            state.get("create_result", {}).get("status") == "success"
            and state.get("validation_result", {}).get("status") == "success"
        )
        state["message"] = "completed" if state["success"] else "completed_with_issues"
        return {
            "status": "success" if state["success"] else "partial",
            "workflow": {
                "langgraph": False,
                "routed_to": routed,
            },
            "create_result": state.get("create_result"),
            "validation_result": state.get("validation_result"),
            "quality_result": state.get("quality_result"),
            "issues": state.get("issues", []),
            "message": state.get("message", ""),
        }

    def _should_run_quality(self, state: UCMWorkflowState) -> bool:
        if not state.get("run_quality_check", True):
            return False
        vr = state.get("validation_result", {})
        if vr.get("status") != "success":
            return True
        metrics = vr.get("metrics", {}) if isinstance(vr, dict) else {}
        missing = int(metrics.get("missing_dp_references_in_ucm", 0) or 0)
        # Run quality when validation failed or UCM has missing DP refs
        return missing > 0

    def _run_workflow_with_langgraph(self, initial: UCMWorkflowState) -> Dict[str, Any]:
        """LangGraph StateGraph execution."""

        def route_node(state: UCMWorkflowState) -> Dict[str, Any]:
            return {"route": self.router.route(state)}

        def create_node(state: UCMWorkflowState) -> Dict[str, Any]:
            result = self.creation_agent.create_mappings(
                source_standard=state["source_standard"],
                target_standard=state["target_standard"],
                vector_threshold=state["vector_threshold"],
                structural_threshold=state["structural_threshold"],
                final_threshold=state["final_threshold"],
                batch_size=state["batch_size"],
                dry_run=state["dry_run"],
            )
            return {"create_result": result}

        def validate_node(_state: UCMWorkflowState) -> Dict[str, Any]:
            return {"validation_result": self.validation_agent.validate()}

        def quality_node(state: UCMWorkflowState) -> Dict[str, Any]:
            result = self.quality_check_agent.summarize(
                create_result=state.get("create_result"),
                validation_result=state.get("validation_result"),
            )
            return {"quality_result": result, "issues": result.get("issues", [])}

        def final_node(state: UCMWorkflowState) -> Dict[str, Any]:
            success = (
                state.get("create_result", {}).get("status") == "success"
                and state.get("validation_result", {}).get("status") == "success"
            )
            msg = "completed" if success else "completed_with_issues"
            return {"success": success, "message": msg}

        def route_decision(state: UCMWorkflowState) -> str:
            return state.get("route", "creation_agent")

        def quality_decision(state: UCMWorkflowState) -> str:
            return "quality" if self._should_run_quality(state) else "finalize"

        workflow = StateGraph(UCMWorkflowState)
        workflow.add_node("route", route_node)
        workflow.add_node("create", create_node)
        workflow.add_node("validate", validate_node)
        workflow.add_node("quality", quality_node)
        workflow.add_node("finalize", final_node)
        workflow.set_entry_point("route")
        workflow.add_conditional_edges(
            "route",
            route_decision,
            {"creation_agent": "create", "validation_agent": "validate"},
        )
        workflow.add_edge("create", "validate")
        workflow.add_conditional_edges(
            "validate",
            quality_decision,
            {"quality": "quality", "finalize": "finalize"},
        )
        workflow.add_edge("quality", "finalize")
        workflow.add_edge("finalize", END)
        app = workflow.compile()
        result = app.invoke(initial)
        return {
            "status": "success" if result.get("success") else "partial",
            "workflow": {
                "langgraph": True,
                "routed_to": result.get("route"),
            },
            "create_result": result.get("create_result"),
            "validation_result": result.get("validation_result"),
            "quality_result": result.get("quality_result"),
            "issues": result.get("issues", []),
            "message": result.get("message", ""),
        }


