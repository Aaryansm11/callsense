"""Rubric v1: dimensions, weights, tag severities, composite + compliance cap
(rubric §6.1, §6.2, §8.2, §8.3).
"""

from __future__ import annotations

from db.models import FlagSeverity, FlagTag, RubricDimension

RUBRIC_VERSION = "v1"

DIMENSION_WEIGHTS: dict[RubricDimension, float] = {
    RubricDimension.needs_discovery: 0.25,
    RubricDimension.product_knowledge: 0.15,
    RubricDimension.objection_handling: 0.20,
    RubricDimension.compliance_integrity: 0.25,
    RubricDimension.next_step_booking: 0.15,
}

TAG_SEVERITY: dict[FlagTag, FlagSeverity] = {
    FlagTag.no_needs_discovery: FlagSeverity.warn,
    FlagTag.over_promising: FlagSeverity.critical,
    FlagTag.pressure_tactics: FlagSeverity.critical,
    FlagTag.price_before_value: FlagSeverity.warn,
    FlagTag.undisclosed_costs: FlagSeverity.critical,
    FlagTag.weak_trial_booking: FlagSeverity.warn,
    FlagTag.talk_over_customer: FlagSeverity.info,
    FlagTag.pii_exposure: FlagSeverity.warn,
    FlagTag.non_sales_call: FlagSeverity.info,
}

CRITICAL_TAGS = {t for t, s in TAG_SEVERITY.items() if s is FlagSeverity.critical}

COMPLIANCE_CAP = 40.0
# Below this self-reported confidence a flag is stored as `info` for review
# rather than surfaced as a violation (precision-over-recall; rubric §2.10).
CONFIDENCE_THRESHOLD = 0.6


def compute_composite(
    scores: dict[RubricDimension, int], has_critical_flag: bool
) -> tuple[float, bool]:
    """Return (composite 0-100, was_capped). A critical compliance flag caps the
    composite at 40 regardless of the other dimensions — mis-selling can't be
    averaged away."""
    raw = sum(
        (scores.get(dim, 0) / 5.0) * weight
        for dim, weight in DIMENSION_WEIGHTS.items()
    ) * 100.0
    if has_critical_flag:
        return round(min(raw, COMPLIANCE_CAP), 2), raw > COMPLIANCE_CAP
    return round(raw, 2), False
