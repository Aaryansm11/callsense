"""Recompute a call's materialised composite from its stored scores + live flag
states. A dismissed critical flag no longer caps the composite (false positive
removed); an upheld one keeps the cap. Called after a dispute resolves.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from analysis.rubric import RUBRIC_VERSION, compute_composite
from db.models import RubricDimension


def recompute_call_score(session: Session, call_id: int) -> tuple[float, bool] | None:
    dim_rows = session.execute(
        text(
            "SELECT dimension, raw_score FROM scores "
            "WHERE call_id = :id AND rubric_version = :rv"
        ),
        {"id": call_id, "rv": RUBRIC_VERSION},
    ).all()
    if not dim_rows:
        return None
    dim_scores = {RubricDimension(r.dimension): r.raw_score for r in dim_rows}

    # A critical flag caps the score unless it has been dismissed.
    has_critical = bool(
        session.execute(
            text(
                "SELECT 1 FROM flags WHERE call_id = :id "
                "AND severity = 'critical' AND state <> 'dismissed' LIMIT 1"
            ),
            {"id": call_id},
        ).first()
    )
    composite, capped = compute_composite(dim_scores, has_critical)
    session.execute(
        text(
            "UPDATE call_scores SET composite = :c, compliance_capped = :cap, "
            "computed_at = now() WHERE call_id = :id"
        ),
        {"c": composite, "cap": capped, "id": call_id},
    )
    return composite, capped
