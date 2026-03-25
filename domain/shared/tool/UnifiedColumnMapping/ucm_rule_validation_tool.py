"""§2-2 Rule validation tool — datapoint structure + rulebook hints."""

from __future__ import annotations

from typing import Any, List, Set

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.domain.v1.esg_data.spokes.infra.ucm_pipeline_contracts import (
    EmbeddingCandidateItem,
    RuleCandidateResult,
    RuleValidationResult,
    RuleViolation,
)


def _dp_type_str(v: Any) -> str:
    if v is None:
        return ""
    return v.value if hasattr(v, "value") else str(v)


def _unit_str(v: Any) -> str | None:
    if v is None:
        return None
    return v.value if hasattr(v, "value") else str(v)


def _req_str(v: Any) -> str | None:
    if v is None:
        return None
    return v.value if hasattr(v, "value") else str(v)


def _key_terms_from_validation_rules(vr: Any) -> List[str]:
    if not vr:
        return []
    if isinstance(vr, dict):
        kt = vr.get("key_terms")
        if isinstance(kt, list):
            return [str(x) for x in kt]
    return []


class RuleValidationTool:
    """Score and filter candidates using DP metadata and linked rulebooks."""

    def run(
        self,
        db: Session,
        service: Any,
        *,
        source_dp_id: str,
        candidates: List[EmbeddingCandidateItem],
    ) -> RuleValidationResult:
        from backend.domain.v1.esg_data.models.bases import DataPoint, Rulebook

        source = (
            db.query(DataPoint)
            .filter(DataPoint.dp_id == source_dp_id, DataPoint.is_active.is_(True))
            .first()
        )
        if not source:
            return {
                "status": "error",
                "source_dp_id": source_dp_id,
                "per_candidate": [],
                "message": f"source dp not found: {source_dp_id}",
            }

        primary_ids = {
            rid
            for (rid,) in db.query(Rulebook.rulebook_id)
            .filter(Rulebook.is_active.is_(True), Rulebook.primary_dp_id == source_dp_id)
            .all()
        }
        related_ids_rows = db.execute(
            text(
                """
                SELECT rulebook_id
                FROM rulebooks
                WHERE is_active = TRUE
                  AND :source_dp_id = ANY(related_dp_ids)
                """
            ),
            {"source_dp_id": source_dp_id},
        ).fetchall()
        related_ids = {row[0] for row in related_ids_rows}
        matched_rulebook_ids = primary_ids | related_ids
        if matched_rulebook_ids:
            rulebooks = (
                db.query(Rulebook)
                .filter(Rulebook.is_active.is_(True), Rulebook.rulebook_id.in_(matched_rulebook_ids))
                .all()
            )
        else:
            rulebooks = []

        related_ids: Set[str] = {source_dp_id}
        key_terms: Set[str] = set()
        for rb in rulebooks:
            if rb.related_dp_ids:
                related_ids.update(rb.related_dp_ids)
            key_terms.update(_key_terms_from_validation_rules(rb.validation_rules))
            if rb.key_terms:
                key_terms.update(str(t).lower() for t in rb.key_terms)

        per: List[RuleCandidateResult] = []
        for c in candidates:
            tid = c["target_dp_id"]
            target = (
                db.query(DataPoint)
                .filter(DataPoint.dp_id == tid, DataPoint.is_active.is_(True))
                .first()
            )
            if not target:
                per.append(
                    {
                        "target_dp_id": tid,
                        "rule_pass": False,
                        "rule_score": 0.0,
                        "structure_score": 0.0,
                        "requirement_score": 0.0,
                        "violations": [
                            {
                                "type": "missing_target_dp",
                                "severity": "critical",
                                "detail": tid,
                            }
                        ],
                    }
                )
                continue

            structural_score, match_details = service._calculate_structural_match(source, target)
            violations: List[RuleViolation] = []

            st = _dp_type_str(source.dp_type)
            tt = _dp_type_str(target.dp_type)
            if st and tt and st != tt:
                sev = "critical" if {st, tt} == {"quantitative", "narrative"} else "warning"
                violations.append(
                    {
                        "type": "data_type_mismatch",
                        "severity": sev,
                        "detail": f"{st} vs {tt}",
                    }
                )

            su, tu = _unit_str(source.unit), _unit_str(target.unit)
            if st == "quantitative" and tt == "quantitative" and su and tu and su != tu:
                compatible = service._are_units_compatible(su, tu)
                if not compatible:
                    violations.append(
                        {
                            "type": "unit_mismatch",
                            "severity": "critical",
                            "detail": f"{su} vs {tu}",
                        }
                    )

            if source.category != target.category:
                violations.append(
                    {
                        "type": "category_mismatch",
                        "severity": "warning",
                        "detail": f"{source.category} vs {target.category}",
                    }
                )

            critical = any(v["severity"] == "critical" for v in violations)
            rule_pass = not critical

            text_blob = " ".join(
                filter(
                    None,
                    [
                        (source.description or ""),
                        (target.description or ""),
                        source.name_ko or "",
                        target.name_ko or "",
                    ],
                )
            ).lower()
            overlap = 0
            if key_terms:
                overlap = sum(1 for k in key_terms if k.lower() in text_blob)
                term_score = min(1.0, overlap / max(3, len(key_terms) * 0.15))
            else:
                term_score = 0.5

            related_bonus = 0.15 if tid in related_ids else 0.0
            rule_score = max(0.0, min(1.0, 0.5 * term_score + 0.5 * (1.0 if rule_pass else 0.2) + related_bonus))
            if critical:
                rule_score = min(rule_score, 0.35)

            sr = _req_str(source.disclosure_requirement)
            tr = _req_str(target.disclosure_requirement)
            requirement_score = 1.0 if (sr == "필수" or tr == "필수") else 0.85

            per.append(
                {
                    "target_dp_id": tid,
                    "rule_pass": rule_pass,
                    "rule_score": round(rule_score, 4),
                    "structure_score": round(float(structural_score), 4),
                    "requirement_score": round(requirement_score, 4),
                    "violations": violations,
                    "rule_evidence": {
                        "rulebook_count": len(rulebooks),
                        "key_term_overlap": overlap,
                        "structural_match_details": match_details,
                    },
                }
            )

        return {"status": "success", "source_dp_id": source_dp_id, "per_candidate": per}
