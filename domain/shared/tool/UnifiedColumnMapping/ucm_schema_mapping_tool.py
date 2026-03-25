"""§2-5 Schema mapping tool — UCM upsert payload (no DB IO)."""

from __future__ import annotations

from typing import Any, List

from backend.domain.v1.esg_data.spokes.infra.ucm_pipeline_contracts import (
    DecisionResult,
    SchemaMappingResult,
    UCMPayload,
)


def _str_enum(v: Any) -> str | None:
    if v is None:
        return None
    return v.value if hasattr(v, "value") else str(v)


class SchemaMappingTool:
    """Build unified_column_mappings row payload from DP ORM rows and policy decision."""

    POLICY_VERSION = "ucm_pipeline_v1"

    def build_payload(
        self,
        *,
        source_dp: Any,
        target_dp: Any,
        decision: DecisionResult,
        primary_rulebook_id: str | None = None,
    ) -> SchemaMappingResult:
        if decision.get("decision") == "reject":
            return {
                "status": "error",
                "message": "reject — no UCM payload",
            }

        sid = source_dp.dp_id
        tid = target_dp.dp_id
        # source DP만으로 ID를 만들면 여러 target에 대한 매핑이 덮어써짐.
        # (source,target) 쌍 기반으로 고유 ID를 만든다.
        s = sid.replace("-", "_")
        t = tid.replace("-", "_")
        unified_column_id = f"UCM_{s}__{t}"[:50]

        mapped: List[str] = [sid, tid]
        if mapped[0] == mapped[1]:
            mapped = [sid]

        req = _str_enum(source_dp.disclosure_requirement) or _str_enum(target_dp.disclosure_requirement)
        ctype = _str_enum(source_dp.dp_type) or "narrative"
        unit = _str_enum(source_dp.unit) or _str_enum(target_dp.unit)

        notes_parts: List[str] = list(decision.get("reason_codes") or [])
        if decision.get("decision") == "review":
            notes_parts.append("mapping_status=reviewing")

        payload: UCMPayload = {
            "unified_column_id": unified_column_id,
            "column_name_ko": source_dp.name_ko,
            "column_name_en": source_dp.name_en,
            "column_description": source_dp.description,
            "column_category": source_dp.category,
            "column_topic": source_dp.topic,
            "column_subtopic": source_dp.subtopic,
            "primary_standard": source_dp.standard,
            "primary_rulebook_id": primary_rulebook_id,
            "applicable_standards": list({source_dp.standard, target_dp.standard}),
            "mapped_dp_ids": mapped,
            "mapping_confidence": float(decision.get("confidence", 0.0)),
            "mapping_notes": "; ".join(notes_parts) if notes_parts else None,
            "column_type": ctype,
            "unit": unit,
            "disclosure_requirement": req,
            "reporting_frequency": source_dp.reporting_frequency,
            "financial_linkages": list(source_dp.financial_linkages or []) or None,
            "financial_impact_type": source_dp.financial_impact_type,
            # API 응답/저장 payload는 JSON serializable 이어야 함.
            # pgvector/ndarray/bytes 등은 직렬화 실패를 유발하므로 저장 시 별도 경로로 처리.
            "unified_embedding": None,
            "mapping_status": "accepted" if decision["decision"] == "accept" else "reviewing",
            "reason_codes": list(decision.get("reason_codes") or []),
            "evidence": dict(decision.get("evidence") or {}),
            "policy_version": self.POLICY_VERSION,
        }
        return {"status": "success", "payload": payload}
