"""esg_data UCM service facade — repository 위임 + 배치 매핑 스텁."""

from __future__ import annotations

from typing import Any, Dict

from loguru import logger
from sqlalchemy import text
from backend.domain.v1.esg_data.hub.repositories import UCMRepository
from backend.domain.v1.esg_data.spokes.infra.ucm_pipeline_contracts import (
    UCMWorkflowCreateResult,
    UCMWorkflowValidationResult,
)

_MAPPING_BATCH_REMOVED_MSG = (
    "auto_suggest_mappings_batch / MappingSuggestionService 제거됨 — esg_data에서 하이브리드 매핑 재구현 후 연결하세요."
)


class UCMMappingService:
    """UCM 유스케이스 경계; DB 접근은 UCMRepository에 위임."""

    def __init__(self, repository: UCMRepository | None = None) -> None:
        self.repository = repository or UCMRepository()

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
        logger.warning(_MAPPING_BATCH_REMOVED_MSG)
        return {
            "status": "error",
            "message": _MAPPING_BATCH_REMOVED_MSG,
            "source_standard": source_standard,
            "target_standard": target_standard,
        }

    def suggest_mappings(
        self,
        source_standard: str,
        target_standard: str,
        vector_threshold: float = 0.70,
        structural_threshold: float = 0.50,
        final_threshold: float = 0.75,
        limit: int = 100,
    ) -> Dict[str, Any]:
        logger.warning(_MAPPING_BATCH_REMOVED_MSG)
        return {
            "status": "error",
            "message": _MAPPING_BATCH_REMOVED_MSG,
            "source_standard": source_standard,
            "target_standard": target_standard,
        }

    def upsert_ucm_from_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """SchemaMappingTool payload → unified_column_mappings upsert."""
        return self.repository.upsert_ucm_from_payload(payload)

    def validate_mappings(self) -> UCMWorkflowValidationResult:
        """UCM·data_points 정합성 요약 통계."""
        return self.repository.validate_mappings()

    # --- Tool support methods (EmbeddingCandidateTool / RuleValidationTool) ---
    def _are_units_compatible(self, source_unit: str, target_unit: str) -> bool:
        if source_unit == target_unit:
            return True
        groups = [
            {"currency_krw", "currency_usd"},
            {"tco2e"},
            {"mwh"},
            {"cubic_meter"},
            {"percentage"},
            {"count"},
            {"text"},
        ]
        for group in groups:
            if source_unit in group and target_unit in group:
                return True
        return False

    def _calculate_structural_match(self, source: Any, target: Any) -> tuple[float, dict[str, Any]]:
        score = 0.0
        details: dict[str, Any] = {}

        same_category = source.category == target.category
        same_topic = (source.topic or "") == (target.topic or "")
        same_subtopic = (source.subtopic or "") == (target.subtopic or "")
        same_type = str(getattr(source.dp_type, "value", source.dp_type)) == str(
            getattr(target.dp_type, "value", target.dp_type)
        )

        score += 0.40 if same_category else 0.0
        score += 0.25 if same_topic else 0.0
        score += 0.15 if same_subtopic else 0.0
        score += 0.20 if same_type else 0.0

        details["same_category"] = same_category
        details["same_topic"] = same_topic
        details["same_subtopic"] = same_subtopic
        details["same_dp_type"] = same_type
        return round(score, 4), details

    def find_similar_dps_hybrid(
        self,
        source_dp_id: str,
        target_standard: str,
        *,
        vector_threshold: float = 0.70,
        structural_threshold: float = 0.50,
        final_threshold: float = 0.75,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Simple in-process hybrid search fallback for UCM tools."""
        _ = vector_threshold
        db = None
        try:
            from backend.domain.v1.esg_data.models.bases import DataPoint

            from backend.core.db import get_session

            db = get_session()

            source = (
                db.query(DataPoint)
                .filter(DataPoint.dp_id == source_dp_id, DataPoint.is_active.is_(True))
                .first()
            )
            if not source:
                return []

            targets = (
                db.query(DataPoint)
                .filter(
                    DataPoint.standard == target_standard,
                    DataPoint.is_active.is_(True),
                    DataPoint.dp_id != source_dp_id,
                )
                .all()
            )

            rows: list[dict[str, Any]] = []
            for target in targets:
                structural_score, details = self._calculate_structural_match(source, target)
                # Vector score fallback: use 0.0 when no embedding similarity infra is wired.
                vector_similarity = 0.0
                final_score = round(0.6 * structural_score + 0.4 * vector_similarity, 4)
                if structural_score < structural_threshold or final_score < final_threshold:
                    continue
                rows.append(
                    {
                        "target_dp_id": target.dp_id,
                        "vector_similarity": vector_similarity,
                        "structural_score": structural_score,
                        "final_score": final_score,
                        "match_details": details,
                    }
                )

            rows.sort(key=lambda r: r["final_score"], reverse=True)
            return rows[:top_k]
        except Exception:
            logger.exception("find_similar_dps_hybrid 실패")
            return []
        finally:
            if db is not None:
                db.close()

    def find_similar_dps_cross_standard(
        self,
        source_dp_id: str,
        *,
        vector_threshold: float = 0.70,
        structural_threshold: float = 0.50,
        final_threshold: float = 0.75,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """pgvector(<->)로 '다른 기준서만' 최근접 후보를 찾는다. (중복 매핑 허용)"""
        db = None
        try:
            from backend.domain.v1.esg_data.models.bases import DataPoint
            from backend.core.db import get_session

            db = get_session()
            source = (
                db.query(DataPoint)
                .filter(DataPoint.dp_id == source_dp_id, DataPoint.is_active.is_(True))
                .first()
            )
            if not source:
                return []

            # embedding 컬럼이 vector가 아니면(또는 null이면) 구조 점수 기반 폴백
            if getattr(source, "embedding", None) is None:
                return self._cross_standard_structural_fallback(
                    source, structural_threshold=structural_threshold, final_threshold=final_threshold, top_k=top_k
                )

            # pgvector distance: smaller is closer. Convert to similarity in [0,1] approximately.
            sql = """
            SELECT t.dp_id AS target_dp_id,
                   (s.embedding <-> t.embedding) AS distance
            FROM data_points s
            JOIN data_points t
              ON t.is_active = TRUE
             AND t.dp_id <> s.dp_id
             AND t.standard <> s.standard
             AND t.embedding IS NOT NULL
            WHERE s.dp_id = :source_dp_id
              AND s.is_active = TRUE
              AND s.embedding IS NOT NULL
            ORDER BY s.embedding <-> t.embedding ASC
            LIMIT :top_k
            """
            rows = db.execute(text(sql), {"source_dp_id": source_dp_id, "top_k": int(top_k)}).fetchall()

            # Load targets for structural scoring
            target_ids = [r[0] for r in rows]
            if not target_ids:
                return []
            targets = (
                db.query(DataPoint)
                .filter(DataPoint.dp_id.in_(target_ids), DataPoint.is_active.is_(True))
                .all()
            )
            by_id = {t.dp_id: t for t in targets}

            out: list[dict[str, Any]] = []
            for r in rows:
                tid = r[0]
                dist = float(r[1] or 0.0)
                # Similarity heuristic
                vector_similarity = max(0.0, min(1.0, 1.0 / (1.0 + dist)))
                target = by_id.get(tid)
                if not target:
                    continue
                structural_score, details = self._calculate_structural_match(source, target)
                final_score = round(0.6 * structural_score + 0.4 * vector_similarity, 4)
                if vector_similarity < vector_threshold or structural_score < structural_threshold or final_score < final_threshold:
                    continue
                out.append(
                    {
                        "target_dp_id": tid,
                        "vector_similarity": round(vector_similarity, 6),
                        "structural_score": structural_score,
                        "final_score": final_score,
                        "match_details": {
                            **details,
                            "distance": dist,
                            "same_standard_filtered": True,
                        },
                    }
                )
            out.sort(key=lambda x: x["final_score"], reverse=True)
            return out[:top_k]
        except Exception:
            logger.exception("find_similar_dps_cross_standard 실패")
            return []
        finally:
            if db is not None:
                db.close()

    def _cross_standard_structural_fallback(
        self,
        source: Any,
        *,
        structural_threshold: float,
        final_threshold: float,
        top_k: int,
    ) -> list[dict[str, Any]]:
        """embedding이 없을 때: 다른 기준서만 구조 점수로 후보를 뽑는다."""
        from backend.domain.v1.esg_data.models.bases import DataPoint
        from backend.core.db import get_session

        db = get_session()
        try:
            targets = (
                db.query(DataPoint)
                .filter(
                    DataPoint.is_active.is_(True),
                    DataPoint.standard != source.standard,
                    DataPoint.dp_id != source.dp_id,
                )
                .all()
            )
            rows: list[dict[str, Any]] = []
            for target in targets:
                structural_score, details = self._calculate_structural_match(source, target)
                vector_similarity = 0.0
                final_score = round(0.6 * structural_score + 0.4 * vector_similarity, 4)
                if structural_score < structural_threshold or final_score < final_threshold:
                    continue
                rows.append(
                    {
                        "target_dp_id": target.dp_id,
                        "vector_similarity": vector_similarity,
                        "structural_score": structural_score,
                        "final_score": final_score,
                        "match_details": {**details, "same_standard_filtered": True},
                    }
                )
            rows.sort(key=lambda r: r["final_score"], reverse=True)
            return rows[:top_k]
        finally:
            db.close()
