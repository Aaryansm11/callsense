"""Stage 6: VALIDATE — final invariant gate before a call is surfaced.

Asserts the analysis is complete and consistent (a materialised composite exists
and all rubric dimensions were scored). Passing calls go `done`; anything partial
goes `needs_review` rather than being shown as if it were fully analysed.
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from analysis.rubric import DIMENSION_WEIGHTS
from db.models import CallStatus
from pipeline.stages.base import set_call_status

log = logging.getLogger("callsense.stage.validate")


def run(session: Session, call_id: int) -> None:
    has_composite = session.execute(
        text("SELECT 1 FROM call_scores WHERE call_id = :id"), {"id": call_id}
    ).first()
    n_dims = session.execute(
        text("SELECT count(*) FROM scores WHERE call_id = :id"), {"id": call_id}
    ).scalar_one()

    ok = bool(has_composite) and n_dims == len(DIMENSION_WEIGHTS)
    status = CallStatus.done.value if ok else CallStatus.needs_review.value
    set_call_status(session, call_id, status)
    log.info("call %s validated -> %s (dims=%d)", call_id, status, n_dims)
