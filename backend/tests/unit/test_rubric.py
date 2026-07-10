"""Composite + compliance-cap unit tests (rubric §8.2, §8.3)."""

import pytest

from analysis.rubric import DIMENSION_WEIGHTS, compute_composite
from db.models import RubricDimension as D


def _all(score: int) -> dict:
    return {dim: score for dim in DIMENSION_WEIGHTS}


def test_weights_sum_to_one():
    assert abs(sum(DIMENSION_WEIGHTS.values()) - 1.0) < 1e-9


def test_perfect_score_is_100():
    composite, capped = compute_composite(_all(5), has_critical_flag=False)
    assert composite == 100.0 and capped is False


def test_smooth_talker_is_capped_at_40():
    # High dimensions (~68) but a critical flag caps to 40 — charm can't launder
    # mis-selling.
    scores = {
        D.needs_discovery: 4, D.product_knowledge: 4, D.objection_handling: 3,
        D.compliance_integrity: 1, D.next_step_booking: 5,
    }
    uncapped, _ = compute_composite(scores, has_critical_flag=False)
    capped_val, was_capped = compute_composite(scores, has_critical_flag=True)
    assert uncapped > 40
    assert capped_val == 40.0 and was_capped is True


def test_already_low_score_with_critical_not_raised():
    composite, capped = compute_composite(_all(1), has_critical_flag=True)
    assert composite == 20.0 and capped is False  # 20 < 40, cap doesn't lift it
