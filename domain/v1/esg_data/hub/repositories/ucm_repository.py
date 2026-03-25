"""UCM/DataPoint persistence access for esg_data."""

from __future__ import annotations

from typing import Any, Dict

from loguru import logger
from sqlalchemy import text

from backend.core.db import get_session
from backend.domain.v1.esg_data.models.bases import DataPoint, UnifiedColumnMapping
from backend.domain.v1.esg_data.spokes.infra.ucm_pipeline_contracts import (
    UCMWorkflowValidationResult,
)


class UCMRepository:
    """Repository for unified_column_mappings and related DataPoint checks."""

    def upsert_ucm_from_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        db = None
        try:
            skip = frozenset({"reason_codes", "evidence", "policy_version", "mapping_status"})
            db = get_session()
            uid = payload["unified_column_id"]
            existing = (
                db.query(UnifiedColumnMapping)
                .filter(UnifiedColumnMapping.unified_column_id == uid)
                .first()
            )
            col_names = {c.name for c in UnifiedColumnMapping.__table__.columns}
            data = {
                k: v
                for k, v in payload.items()
                if k in col_names and k != "unified_column_id" and k not in skip
            }
            if existing:
                for key, value in data.items():
                    setattr(existing, key, value)
                mode = "update"
            else:
                row = UnifiedColumnMapping(unified_column_id=uid, **data)
                db.add(row)
                mode = "create"
            db.commit()
            return {"status": "success", "unified_column_id": uid, "mode": mode}
        except Exception as e:
            logger.exception("UCM upsert 실패")
            if db is not None:
                db.rollback()
            return {
                "status": "error",
                "message": str(e),
                "unified_column_id": payload.get("unified_column_id"),
            }
        finally:
            if db is not None:
                db.close()

    def validate_mappings(self) -> UCMWorkflowValidationResult:
        """UCM·data_points 정합성 요약 통계."""
        db = None
        try:
            db = get_session()

            total_dp = db.query(DataPoint).filter(DataPoint.is_active.is_(True)).count()
            mapped_equivalent = db.query(DataPoint).filter(
                DataPoint.is_active.is_(True),
                DataPoint.equivalent_dps.isnot(None),
            ).count()
            total_ucm = db.query(UnifiedColumnMapping).filter(
                UnifiedColumnMapping.is_active.is_(True)
            ).count()

            missing_dp_rows = db.execute(
                text(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM unified_column_mappings ucm
                    LEFT JOIN LATERAL unnest(ucm.mapped_dp_ids) AS m(dp_id) ON TRUE
                    LEFT JOIN data_points dp ON dp.dp_id = m.dp_id
                    WHERE ucm.is_active = TRUE
                      AND dp.dp_id IS NULL
                    """
                )
            ).scalar() or 0

            coverage = round((mapped_equivalent / total_dp) * 100, 2) if total_dp else 0.0
            return {
                "status": "success",
                "metrics": {
                    "active_data_points": total_dp,
                    "mapped_data_points_by_equivalent_dps": mapped_equivalent,
                    "mapping_coverage_percent": coverage,
                    "active_unified_column_mappings": total_ucm,
                    "missing_dp_references_in_ucm": int(missing_dp_rows),
                },
            }
        except Exception as e:
            logger.exception("UCM 헬스체크 실패")
            return {"status": "error", "message": str(e)}
        finally:
            if db is not None:
                db.close()
