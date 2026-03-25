"""§2-1 Embedding candidate tool — hybrid DP similarity search."""

from __future__ import annotations

from typing import Any, List, Optional

from sqlalchemy.orm import Session

from backend.domain.v1.esg_data.spokes.infra.ucm_pipeline_contracts import (
    EmbeddingCandidateItem,
    EmbeddingCandidateResult,
)


class EmbeddingCandidateTool:
    """Vector + structural hybrid search for cross-standard DP candidates."""

    def run(
        self,
        db: Session,
        service: Any,
        *,
        source_dp_id: str,
        target_standard: Optional[str],
        top_k: int = 5,
        vector_threshold: float = 0.70,
        structural_threshold: float = 0.50,
        final_threshold: float = 0.75,
    ) -> EmbeddingCandidateResult:
        if target_standard:
            rows = service.find_similar_dps_hybrid(
                source_dp_id,
                target_standard,
                vector_threshold=vector_threshold,
                structural_threshold=structural_threshold,
                final_threshold=final_threshold,
                top_k=top_k,
            )
            target_label = target_standard
        else:
            rows = service.find_similar_dps_cross_standard(
                source_dp_id,
                vector_threshold=vector_threshold,
                structural_threshold=structural_threshold,
                final_threshold=final_threshold,
                top_k=top_k,
            )
            target_label = "*"
        candidates: List[EmbeddingCandidateItem] = []
        for i, row in enumerate(rows, start=1):
            item: EmbeddingCandidateItem = {
                "target_dp_id": row["target_dp_id"],
                "rank": i,
                "vector_similarity": float(row.get("vector_similarity", 0.0)),
                "structural_score": float(row.get("structural_score", 0.0)),
                "hybrid_score": float(row.get("final_score", 0.0)),
            }
            md = row.get("match_details")
            if isinstance(md, dict):
                item["match_details"] = md
            candidates.append(item)
        return {
            "status": "success",
            "source_dp_id": source_dp_id,
            "target_standard": target_label,
            "candidates": candidates,
        }
