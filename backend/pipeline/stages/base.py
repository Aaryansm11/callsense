"""Shared helpers for pipeline stages.

Each stage is a `run(session, call_id)` callable that is idempotent (skips if its
output already exists) and raises on failure. The worker owns the transaction and
the job-status transitions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from transcription.base import TxSegment


@dataclass
class CallInfo:
    id: int
    audio_uri: str | None
    channels: int | None
    status: str
    fixture: str | None
    raw_metadata: dict


def load_call(session: Session, call_id: int) -> CallInfo:
    row = session.execute(
        text(
            "SELECT id, audio_uri, channels, status, raw_metadata "
            "FROM calls WHERE id = :id"
        ),
        {"id": call_id},
    ).mappings().first()
    if row is None:
        raise ValueError(f"call {call_id} not found")
    raw = row["raw_metadata"] or {}
    return CallInfo(
        id=row["id"],
        audio_uri=row["audio_uri"],
        channels=row["channels"],
        status=row["status"],
        fixture=raw.get("fixture"),
        raw_metadata=raw,
    )


def load_tx_segments(session: Session, call_id: int, redacted: bool = False) -> list[TxSegment]:
    col = "COALESCE(s.redacted_text, s.text)" if redacted else "s.text"
    rows = session.execute(
        text(
            f"""
            SELECT s.idx, s.speaker, s.start_s, s.end_s, {col} AS body
            FROM segments s
            JOIN transcripts t ON t.id = s.transcript_id
            WHERE t.call_id = :cid
            ORDER BY s.idx
            """
        ),
        {"cid": call_id},
    ).mappings().all()
    return [
        TxSegment(
            idx=r["idx"], start_s=r["start_s"], end_s=r["end_s"],
            text=r["body"], speaker=r["speaker"],
        )
        for r in rows
    ]


def set_call_status(session: Session, call_id: int, status: str) -> None:
    session.execute(
        text("UPDATE calls SET status = :s, updated_at = now() WHERE id = :id"),
        {"s": status, "id": call_id},
    )


def merge_raw_metadata(session: Session, call_id: int, patch: dict) -> None:
    session.execute(
        text(
            "UPDATE calls SET raw_metadata = raw_metadata || CAST(:patch AS jsonb), "
            "updated_at = now() WHERE id = :id"
        ),
        {"patch": json.dumps(patch), "id": call_id},
    )
