"""UCM policy scoring and decision (§2-4) — pure logic, no DB."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from backend.domain.v1.esg_data.spokes.infra.ucm_pipeline_contracts import (
    DecisionResult,
    EmbeddingCandidateItem,
    LLMRefinementResult,
    RuleCandidateResult,
    RuleViolation,
)


def compute_penalty(violations: List[RuleViolation]) -> float:
    p = 0.0
    for v in violations:
        if v["severity"] == "critical":
            if v["type"] in ("unit_mismatch", "data_type_mismatch", "missing_target_dp"):
                p += 0.20
            else:
                p += 0.15
        else:
            p += 0.05
    return min(0.50, p)


def compute_final_score(
    hybrid_score: float,
    rule_score: float,
    structure_score: float,
    requirement_score: float,
    penalty: float,
) -> float:
    raw = (
        0.50 * hybrid_score
        + 0.30 * rule_score
        + 0.10 * structure_score
        + 0.10 * requirement_score
        - penalty
    )
    return max(0.0, min(1.0, raw))


def tentative_decision_from_scores(final_score: float, has_critical: bool) -> str:
    if has_critical:
        return "reject"
    if final_score >= 0.85:
        return "accept"
    if final_score < 0.60:
        return "reject"
    return "review"


def should_call_llm(hybrid_score: float, rule_pass: bool, tentative: str) -> bool:
    if tentative != "review":
        return False
    if not rule_pass:
        return False
    return 0.65 <= hybrid_score <= 0.82


def merge_candidate_rule(
    cand: EmbeddingCandidateItem,
    per_rule: List[RuleCandidateResult],
) -> RuleCandidateResult | None:
    tid = cand["target_dp_id"]
    for row in per_rule:
        if row["target_dp_id"] == tid:
            return row
    return None


def decide_mapping_pair(
    *,
    source_dp_id: str,
    candidate: EmbeddingCandidateItem,
    rule_row: RuleCandidateResult,
    llm_result: LLMRefinementResult | None,
    policy_version: str,
) -> DecisionResult:
    hybrid = float(candidate["hybrid_score"])
    violations = list(rule_row["violations"])
    has_critical = any(v["severity"] == "critical" for v in violations)
    penalty = compute_penalty(violations)
    final_score = compute_final_score(
        hybrid,
        float(rule_row["rule_score"]),
        float(rule_row["structure_score"]),
        float(rule_row["requirement_score"]),
        penalty,
    )

    tentative = tentative_decision_from_scores(final_score, has_critical)
    llm_used = bool(llm_result and llm_result.get("llm_used"))
    reason_codes: List[str] = []
    evidence: Dict[str, Any] = {
        "policy_version": policy_version,
        "hybrid_score": hybrid,
        "rule_score": rule_row["rule_score"],
        "structure_score": rule_row["structure_score"],
        "requirement_score": rule_row["requirement_score"],
        "penalty": penalty,
        "violations": [dict(v) for v in violations],
    }

    if llm_result and llm_result.get("status") == "success" and llm_result.get("refinement_score") is not None:
        rs = float(llm_result["refinement_score"])
        final_score = max(0.0, min(1.0, 0.85 * final_score + 0.15 * rs))
        evidence["llm_refinement_score"] = rs
        tentative = tentative_decision_from_scores(final_score, has_critical)

    if has_critical:
        reason_codes.append("critical_violation")
    if not rule_row["rule_pass"]:
        reason_codes.append("rule_fail")

    decision = tentative
    if decision == "accept":
        reason_codes.append("auto_accept_threshold")
    elif decision == "review":
        reason_codes.append("manual_review_band")
    else:
        reason_codes.append("auto_reject_threshold")

    return {
        "decision": decision,  # type: ignore[assignment]
        "confidence": round(final_score, 4),
        "reason_codes": reason_codes,
        "llm_used": llm_used,
        "evidence": evidence,
        "chosen_target_dp_id": rule_row["target_dp_id"],
        "final_score": round(final_score, 4),
    }


def build_reject_decision(source_dp_id: str, code: str, extra: Dict[str, Any] | None = None) -> DecisionResult:
    ev: Dict[str, Any] = {"source_dp_id": source_dp_id}
    if extra:
        ev.update(extra)
    return {
        "decision": "reject",
        "confidence": 0.0,
        "reason_codes": [code],
        "llm_used": False,
        "evidence": ev,
    }


def pick_best_candidate_pair(
    candidates: List[EmbeddingCandidateItem],
    per_rule: List[RuleCandidateResult],
) -> Tuple[EmbeddingCandidateItem, RuleCandidateResult] | None:
    best: Tuple[EmbeddingCandidateItem, RuleCandidateResult, float] | None = None
    for cand in sorted(candidates, key=lambda c: c["hybrid_score"], reverse=True):
        rr = merge_candidate_rule(cand, per_rule)
        if rr is None:
            continue
        violations = rr["violations"]
        has_critical = any(v["severity"] == "critical" for v in violations)
        penalty = compute_penalty(violations)
        fs = compute_final_score(
            float(cand["hybrid_score"]),
            float(rr["rule_score"]),
            float(rr["structure_score"]),
            float(rr["requirement_score"]),
            penalty,
        )
        if has_critical:
            continue
        if best is None or fs > best[2]:
            best = (cand, rr, fs)
    return (best[0], best[1]) if best else None
