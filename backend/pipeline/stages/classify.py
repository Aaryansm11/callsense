"""Stage 4: CLASSIFY — sales vs non-sales (cheap cascade before full analysis).

Non-sales calls (wrong number / internal) are tagged and finalised WITHOUT a
composite score, so they are excluded from every rollup average and don't burn
analysis tokens (rubric §2.15, §6.4).
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from analysis.llm import get_llm
from db.models import CallStatus, FlagSeverity, FlagState, FlagTag
from pipeline.stages.base import load_call, load_tx_segments, set_call_status

log = logging.getLogger("callsense.stage.classify")

OPENING_TURNS = 12


def run(session: Session, call_id: int) -> None:
    # Idempotent: if already tagged non-sales, nothing to do.
    already = session.execute(
        text(
            "SELECT 1 FROM flags WHERE call_id = :id AND tag = :t"
        ),
        {"id": call_id, "t": FlagTag.non_sales_call.value},
    ).first()
    if already:
        return

    call = load_call(session, call_id)
    segments = load_tx_segments(session, call_id, redacted=True)
    opening = "\n".join(
        f"{s.speaker}: {s.text}" for s in segments[:OPENING_TURNS]
    )

    llm = get_llm(call.fixture)
    if llm.is_sales_call(opening):
        log.info("call %s classified as SALES", call_id)
        return

    # Non-sales: tag + finalise, no scoring.
    first_quote = segments[0].text if segments else None
    session.execute(
        text(
            """
            INSERT INTO flags
                (call_id, tag, severity, quote, reason, confidence, state, created_at)
            VALUES (:cid, :tag, :sev, :q, :reason, 1.0, :state, now())
            """
        ),
        {
            "cid": call_id, "tag": FlagTag.non_sales_call.value,
            "sev": FlagSeverity.info.value, "q": first_quote,
            "reason": "Classified as a non-sales call; excluded from scoring.",
            "state": FlagState.open.value,
        },
    )
    set_call_status(session, call_id, CallStatus.done.value)
    log.info("call %s classified as NON_SALES; finalised", call_id)
