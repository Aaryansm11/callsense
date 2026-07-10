"""Stage 3: REDACT — mask PII into redacted_text before the LLM sees anything."""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from analysis.redaction import redact
from pipeline.stages.base import merge_raw_metadata

log = logging.getLogger("callsense.stage.redact")


def run(session: Session, call_id: int) -> None:
    rows = session.execute(
        text(
            """
            SELECT s.id, s.text, s.redacted_text
            FROM segments s JOIN transcripts t ON t.id = s.transcript_id
            WHERE t.call_id = :cid
            """
        ),
        {"cid": call_id},
    ).mappings().all()

    all_found: list[str] = []
    for r in rows:
        if r["redacted_text"] is not None:  # idempotent: already redacted
            continue
        redacted, found = redact(r["text"])
        all_found.extend(found)
        session.execute(
            text("UPDATE segments SET redacted_text = :rt WHERE id = :id"),
            {"rt": redacted, "id": r["id"]},
        )

    if all_found:
        merge_raw_metadata(
            session, call_id, {"pii_redacted": sorted(set(all_found))}
        )
    log.info("call %s redacted (%d segments, pii=%s)", call_id, len(rows),
             sorted(set(all_found)))
