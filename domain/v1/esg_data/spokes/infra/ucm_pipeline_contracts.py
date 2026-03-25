"""UCM policy pipeline + workflow result contracts (TypedDict) — esg_data infra 단일 소스."""

from __future__ import annotations

from typing import Any, List, Literal, NotRequired, TypedDict

# --- §2 policy pipeline (tool / agent step I/O) ---


class EmbeddingCandidateItem(TypedDict):
    target_dp_id: str
    rank: int
    vector_similarity: float
    structural_score: float
    hybrid_score: float
    match_details: NotRequired[dict[str, Any]]


class EmbeddingCandidateResult(TypedDict):
    status: Literal["success", "error"]
    source_dp_id: str
    target_standard: str
    candidates: List[EmbeddingCandidateItem]
    message: NotRequired[str]


class RuleViolation(TypedDict):
    type: str
    severity: Literal["critical", "warning"]
    detail: str


class RuleCandidateResult(TypedDict):
    target_dp_id: str
    rule_pass: bool
    rule_score: float
    structure_score: float
    requirement_score: float
    violations: List[RuleViolation]
    rule_evidence: NotRequired[dict[str, Any]]


class RuleValidationResult(TypedDict):
    status: Literal["success", "error"]
    source_dp_id: str
    per_candidate: List[RuleCandidateResult]
    message: NotRequired[str]


class LLMRefinementResult(TypedDict):
    status: Literal["success", "skipped", "error"]
    refinement_score: NotRequired[float]
    notes: NotRequired[str]
    llm_used: bool


DecisionLiteral = Literal["accept", "review", "reject"]


class DecisionResult(TypedDict):
    decision: DecisionLiteral
    confidence: float
    reason_codes: List[str]
    llm_used: bool
    evidence: dict[str, Any]
    chosen_target_dp_id: NotRequired[str]
    final_score: NotRequired[float]


class UCMPayload(TypedDict, total=False):
    unified_column_id: str
    column_name_ko: str
    column_name_en: str
    column_description: str | None
    column_category: str
    column_topic: str | None
    column_subtopic: str | None
    primary_standard: str
    primary_rulebook_id: str | None
    applicable_standards: List[str]
    mapped_dp_ids: List[str]
    mapping_confidence: float | None
    mapping_notes: str | None
    column_type: str
    unit: str | None
    disclosure_requirement: str | None
    reporting_frequency: str | None
    financial_linkages: List[str] | None
    financial_impact_type: str | None
    unified_embedding: Any
    mapping_status: str
    reason_codes: List[str]
    evidence: dict[str, Any]
    policy_version: str


class SchemaMappingResult(TypedDict):
    status: Literal["success", "error"]
    payload: NotRequired[UCMPayload]
    message: NotRequired[str]


# --- Phase 3 LangGraph / orchestrator agent outputs ---


class UCMWorkflowCreateResult(TypedDict, total=False):
    """`UCMMappingService.create_mappings` / creation agent 배치 결과."""

    status: Literal["success", "error"]
    mode: str
    source_standard: str
    target_standard: str
    stats: dict[str, Any]
    message: str


class UCMWorkflowValidationResult(TypedDict, total=False):
    """`validate_mappings` / validation agent 헬스 결과."""

    status: Literal["success", "error"]
    metrics: dict[str, Any]
    message: str


class UCMQualityIssue(TypedDict, total=False):
    type: str
    message: str
    count: int


class UCMWorkflowQualityResult(TypedDict, total=False):
    """`QualityCheckAgent.summarize` 출력."""

    status: Literal["success", "error"]
    issues_count: int
    issues: List[UCMQualityIssue]


__all__ = [
    "DecisionLiteral",
    "DecisionResult",
    "EmbeddingCandidateItem",
    "EmbeddingCandidateResult",
    "LLMRefinementResult",
    "RuleCandidateResult",
    "RuleValidationResult",
    "RuleViolation",
    "SchemaMappingResult",
    "UCMPayload",
    "UCMQualityIssue",
    "UCMWorkflowCreateResult",
    "UCMWorkflowQualityResult",
    "UCMWorkflowValidationResult",
]
