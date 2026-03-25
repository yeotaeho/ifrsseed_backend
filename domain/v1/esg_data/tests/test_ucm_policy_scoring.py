"""Unit tests for UCM policy scoring (no DB)."""

from __future__ import annotations

from backend.domain.v1.esg_data.spokes.infra.ucm_pipeline_contracts import (
    EmbeddingCandidateItem,
    RuleCandidateResult,
)
from backend.domain.shared.tool.UnifiedColumnMapping import SchemaMappingTool
from backend.domain.v1.esg_data.spokes.agents import ucm_policy


def test_compute_final_score_range():
    s = ucm_policy.compute_final_score(0.8, 0.8, 0.9, 1.0, 0.0)
    assert 0.0 <= s <= 1.0


def test_pick_best_skips_critical():
    cands: list[EmbeddingCandidateItem] = [
        {
            "target_dp_id": "A",
            "rank": 1,
            "vector_similarity": 0.9,
            "structural_score": 0.9,
            "hybrid_score": 0.9,
        },
    ]
    per: list[RuleCandidateResult] = [
        {
            "target_dp_id": "A",
            "rule_pass": False,
            "rule_score": 0.5,
            "structure_score": 0.5,
            "requirement_score": 1.0,
            "violations": [
                {"type": "unit_mismatch", "severity": "critical", "detail": "x"},
            ],
        },
    ]
    assert ucm_policy.pick_best_candidate_pair(cands, per) is None


def test_decide_mapping_pair_accept_high_score():
    cand: EmbeddingCandidateItem = {
        "target_dp_id": "T1",
        "rank": 1,
        "vector_similarity": 0.95,
        "structural_score": 0.95,
        "hybrid_score": 0.95,
    }
    rr: RuleCandidateResult = {
        "target_dp_id": "T1",
        "rule_pass": True,
        "rule_score": 0.92,
        "structure_score": 0.92,
        "requirement_score": 1.0,
        "violations": [],
    }
    out = ucm_policy.decide_mapping_pair(
        source_dp_id="S1",
        candidate=cand,
        rule_row=rr,
        llm_result=None,
        policy_version="test",
    )
    assert out["decision"] == "accept"
    assert out["chosen_target_dp_id"] == "T1"


def test_schema_mapping_reject():
    tool = SchemaMappingTool()
    dec = ucm_policy.build_reject_decision("S1", "x")
    r = tool.build_payload(source_dp=None, target_dp=None, decision=dec, primary_rulebook_id=None)  # type: ignore[arg-type]
    assert r["status"] == "error"
