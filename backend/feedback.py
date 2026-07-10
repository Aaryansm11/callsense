"""Dispute feedback loop (rubric §2.11, §3.14, §8.6).

State machine (enforced): flag open -> disputed -> upheld | dismissed. Resolving
a dispute (a) writes the flag's new state, (b) recomputes the composite (a
dismissed critical flag lifts the compliance cap), (c) mints a calibration example
that tightens future precision, and (d) records the human action in the audit log.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from analysis.recompute import recompute_call_score
from db.models import CalibrationVerdict, FlagState


class DisputeError(ValueError):
    """Illegal state transition (e.g. disputing a non-open flag)."""


@dataclass
class ResolveResult:
    dispute_id: int
    flag_id: int
    call_id: int
    new_state: str
    composite: float | None
    compliance_capped: bool | None


def raise_dispute(
    session: Session, flag_id: int, note: str | None, raised_by: int | None
) -> int:
    flag = session.execute(
        text("SELECT id, call_id, state FROM flags WHERE id = :id"), {"id": flag_id}
    ).mappings().first()
    if flag is None:
        raise DisputeError(f"flag {flag_id} not found")
    if flag["state"] != FlagState.open.value:
        raise DisputeError(
            f"flag {flag_id} is '{flag['state']}', only 'open' flags can be disputed"
        )

    dispute_id = session.execute(
        text(
            "INSERT INTO disputes (flag_id, raised_by, note, created_at) "
            "VALUES (:fid, :by, :note, now()) RETURNING id"
        ),
        {"fid": flag_id, "by": raised_by, "note": note},
    ).scalar_one()
    session.execute(
        text("UPDATE flags SET state = :s WHERE id = :id"),
        {"s": FlagState.disputed.value, "id": flag_id},
    )
    _audit(
        session, actor=f"advisor:{raised_by}" if raised_by else "advisor",
        action="raise_dispute", entity_id=flag_id,
        before={"state": FlagState.open.value},
        after={"state": FlagState.disputed.value, "note": note},
    )
    return dispute_id


def resolve_dispute(
    session: Session,
    dispute_id: int,
    resolution: str,
    resolved_by: str | None,
    resolution_note: str | None,
) -> ResolveResult:
    if resolution not in (FlagState.upheld.value, FlagState.dismissed.value):
        raise DisputeError("resolution must be 'upheld' or 'dismissed'")

    row = session.execute(
        text(
            """
            SELECT d.id AS dispute_id, d.flag_id, f.call_id, f.tag, f.quote,
                   f.state AS flag_state, d.resolved_at
            FROM disputes d JOIN flags f ON f.id = d.flag_id
            WHERE d.id = :id
            """
        ),
        {"id": dispute_id},
    ).mappings().first()
    if row is None:
        raise DisputeError(f"dispute {dispute_id} not found")
    if row["flag_state"] != FlagState.disputed.value:
        raise DisputeError(
            f"flag {row['flag_id']} is '{row['flag_state']}', not 'disputed'"
        )

    session.execute(
        text(
            "UPDATE disputes SET resolution = :r, resolved_by = :by, "
            "resolution_note = :note, resolved_at = now() WHERE id = :id"
        ),
        {"r": resolution, "by": resolved_by, "note": resolution_note, "id": dispute_id},
    )
    session.execute(
        text("UPDATE flags SET state = :s WHERE id = :id"),
        {"s": resolution, "id": row["flag_id"]},
    )

    # Human decision -> calibration few-shot.
    verdict = (
        CalibrationVerdict.true_positive.value
        if resolution == FlagState.upheld.value
        else CalibrationVerdict.false_positive.value
    )
    session.execute(
        text(
            "INSERT INTO calibration_examples "
            "(tag, quote, verdict, source_dispute_id, created_at, updated_at) "
            "VALUES (:tag, :quote, :verdict, :sid, now(), now())"
        ),
        {"tag": row["tag"], "quote": row["quote"], "verdict": verdict, "sid": dispute_id},
    )

    recomputed = recompute_call_score(session, row["call_id"])
    _audit(
        session, actor=resolved_by or "team_leader", action="resolve_dispute",
        entity_id=row["flag_id"],
        before={"state": FlagState.disputed.value},
        after={"state": resolution, "resolution_note": resolution_note},
    )
    return ResolveResult(
        dispute_id=dispute_id,
        flag_id=row["flag_id"],
        call_id=row["call_id"],
        new_state=resolution,
        composite=recomputed[0] if recomputed else None,
        compliance_capped=recomputed[1] if recomputed else None,
    )


def _audit(session: Session, actor, action, entity_id, before, after) -> None:
    session.execute(
        text(
            "INSERT INTO audit_log (actor, action, entity, entity_id, before, after, at) "
            "VALUES (:actor, :action, 'flag', :eid, CAST(:before AS jsonb), "
            "CAST(:after AS jsonb), now())"
        ),
        {
            "actor": actor, "action": action, "eid": str(entity_id),
            "before": json.dumps(before), "after": json.dumps(after),
        },
    )
