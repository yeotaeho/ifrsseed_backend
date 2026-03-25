"""UCM creation agent (Phase 2) + policy hooks + LLM refinement stub (§2-3)."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from backend.domain.v1.esg_data.spokes.infra.ucm_pipeline_contracts import (
    DecisionResult,
    EmbeddingCandidateItem,
    LLMRefinementResult,
    RuleCandidateResult,
    UCMWorkflowCreateResult,
)
from backend.domain.v1.esg_data.spokes.agents import ucm_policy
from backend.domain.v1.esg_data.spokes.infra.ucm_mapping_service import UCMMappingService


class UCMCreationAgent:
    """UCM 생성/추천, 정책 단계, 경계 구간 LLM 재평가(스텁)."""

    def __init__(self, mapping_service: UCMMappingService | None = None) -> None:
        self.mapping_service = mapping_service or UCMMappingService()

    def llm_refinement(self, context: Dict[str, Any]) -> LLMRefinementResult:
        """§2-3: 경계 구간에서 LLM(gpt-5-mini) 보정 점수 계산."""
        model = str(context.get("model") or "gpt-5-mini")
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            return {
                "status": "skipped",
                "notes": f"OPENAI_API_KEY not set ({model})",
                "llm_used": False,
            }

        try:
            from openai import OpenAI
        except ImportError:
            return {
                "status": "error",
                "notes": "openai package is required (pip install openai)",
                "llm_used": False,
            }

        client = OpenAI(api_key=api_key)
        payload = {
            "source_dp_id": context.get("source_dp_id"),
            "target_dp_id": context.get("target_dp_id"),
            "candidate": context.get("candidate", {}),
            "rule_row": context.get("rule_row", {}),
            "tentative_decision": context.get("tentative_decision"),
        }
        system_prompt = (
            "You are a strict ESG mapping judge. "
            "Return ONLY JSON with keys: refinement_score (0~1 float), notes (short string)."
        )
        user_prompt = (
            "Refine mapping confidence for a cross-standard datapoint pair.\n"
            "If evidence is weak, lower score. If strong and consistent, raise score.\n"
            f"Input:\n{json.dumps(payload, ensure_ascii=False)}"
        )
        try:
            resp = client.chat.completions.create(
                model=model,
                temperature=0,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            choice = resp.choices[0] if resp.choices else None
            raw_text = (choice.message.content or "").strip() if choice and choice.message else ""
            data = json.loads(raw_text)
            score = float(data.get("refinement_score"))
            score = max(0.0, min(1.0, score))
            notes = str(data.get("notes") or "")
            return {
                "status": "success",
                "refinement_score": round(score, 4),
                "notes": notes,
                "llm_used": True,
            }
        except Exception as e:
            logger.warning("UCM llm_refinement failed: {}", e)
            return {
                "status": "error",
                "notes": f"llm refinement failed ({model}): {e}",
                "llm_used": False,
            }

    def policy_pick_best(
        self,
        candidates: List[EmbeddingCandidateItem],
        per_rule: List[RuleCandidateResult],
    ) -> Optional[Tuple[EmbeddingCandidateItem, RuleCandidateResult]]:
        return ucm_policy.pick_best_candidate_pair(candidates, per_rule)

    def policy_finalize_decision(
        self,
        *,
        source_dp_id: str,
        candidate: EmbeddingCandidateItem,
        rule_row: RuleCandidateResult,
        llm_result: LLMRefinementResult | None,
        policy_version: str = "ucm_pipeline_v1",
    ) -> DecisionResult:
        return ucm_policy.decide_mapping_pair(
            source_dp_id=source_dp_id,
            candidate=candidate,
            rule_row=rule_row,
            llm_result=llm_result,
            policy_version=policy_version,
        )

    def create_mappings(
        self,
        source_standard: str,
        target_standard: str,
        vector_threshold: float = 0.70,
        structural_threshold: float = 0.50,
        final_threshold: float = 0.75,
        batch_size: int = 40,
        dry_run: bool = False,
    ) -> UCMWorkflowCreateResult:
        """legacy equivalent_dps 배치."""
        return self.mapping_service.create_mappings(
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
    ) -> Dict[str, Any]:  # 배치 후보: 항목 스키마 가변
        """저장 없이 후보만."""
        return self.mapping_service.suggest_mappings(
            source_standard=source_standard,
            target_standard=target_standard,
            vector_threshold=vector_threshold,
            structural_threshold=structural_threshold,
            final_threshold=final_threshold,
            limit=limit,
        )
