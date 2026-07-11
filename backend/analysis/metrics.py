"""Deterministic conversation metrics derived from diarised segments.

Talk ratio = advisor speaking time / (advisor + customer speaking time),
computed by code from segment durations — never by the LLM (rubric §6.3:
timestamps and arithmetic are derived, not generated). Above the threshold the
analyse stage raises a deterministic `talk_over_customer` flag (info severity).
"""

from __future__ import annotations

from transcription.base import TxSegment

TALK_RATIO_THRESHOLD = 0.75


def talk_ratio(segments: list[TxSegment]) -> float | None:
    """Advisor share of total labelled speaking time; None if unknown speakers."""
    advisor = sum(s.end_s - s.start_s for s in segments if s.speaker == "advisor")
    customer = sum(s.end_s - s.start_s for s in segments if s.speaker == "customer")
    total = advisor + customer
    if total <= 0:
        return None
    return round(advisor / total, 3)
