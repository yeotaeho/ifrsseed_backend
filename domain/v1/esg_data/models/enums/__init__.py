"""StrEnum — PG ENUM 값과 동일 (온톨로지·UCM 표현용)."""

from __future__ import annotations

from enum import StrEnum


class DPTypeEnum(StrEnum):
    QUANTITATIVE = "quantitative"
    QUALITATIVE = "qualitative"
    NARRATIVE = "narrative"
    BINARY = "binary"


class DPUnitEnum(StrEnum):
    PERCENTAGE = "percentage"
    COUNT = "count"
    CURRENCY_KRW = "currency_krw"
    CURRENCY_USD = "currency_usd"
    TCO2E = "tco2e"
    MWH = "mwh"
    CUBIC_METER = "cubic_meter"
    TEXT = "text"


class ImpactDirectionEnum(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    VARIABLE = "variable"


class DisclosureRequirementEnum(StrEnum):
    REQUIRED = "필수"
    RECOMMENDED = "권장"
    OPTIONAL = "선택"
    CONDITIONAL = "조건부"


class UnifiedColumnTypeEnum(StrEnum):
    """unified_column_mappings.column_type — dp_type 과 동일 멤버."""

    QUANTITATIVE = "quantitative"
    QUALITATIVE = "qualitative"
    NARRATIVE = "narrative"
    BINARY = "binary"


__all__ = [
    "DPTypeEnum",
    "DPUnitEnum",
    "ImpactDirectionEnum",
    "DisclosureRequirementEnum",
    "UnifiedColumnTypeEnum",
]
