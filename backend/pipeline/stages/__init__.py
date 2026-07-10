"""Pipeline stage registry + the stage-transition graph.

STAGE_ORDER is the linear happy path. The only branch: after CLASSIFY a call
tagged non-sales is already finalised (status=done), so it terminates instead of
proceeding to ANALYSE.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from db.models import CallStatus
from pipeline.stages import (
    analyse,
    classify,
    diarise,
    redact,
    transcribe,
    validate,
)

STAGE_ORDER: list[str] = [
    "transcribe", "diarise", "redact", "classify", "analyse", "validate",
]

STAGES = {
    "transcribe": transcribe.run,
    "diarise": diarise.run,
    "redact": redact.run,
    "classify": classify.run,
    "analyse": analyse.run,
    "validate": validate.run,
}


def next_stage(current: str, session: Session, call_id: int) -> str | None:
    """Return the stage to enqueue after `current`, or None to end the pipeline."""
    if current == "classify":
        status = session.execute(
            text("SELECT status FROM calls WHERE id = :id"), {"id": call_id}
        ).scalar_one_or_none()
        if status == CallStatus.done.value:  # non-sales: finalised in classify
            return None
    idx = STAGE_ORDER.index(current)
    return STAGE_ORDER[idx + 1] if idx + 1 < len(STAGE_ORDER) else None
