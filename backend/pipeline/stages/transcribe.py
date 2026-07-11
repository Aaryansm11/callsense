"""Stage 1: TRANSCRIBE — audio -> transcript + timestamped segments."""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from db.models import CallStatus
from pipeline.stages.base import load_call, set_call_status
from transcription.factory import get_transcriber

log = logging.getLogger("callsense.stage.transcribe")


def run(session: Session, call_id: int) -> None:
    # Idempotent: skip if a transcript already exists.
    exists = session.execute(
        text("SELECT 1 FROM transcripts WHERE call_id = :id"), {"id": call_id}
    ).first()
    if exists:
        log.info("transcript exists for call %s; skipping", call_id)
        return

    call = load_call(session, call_id)
    set_call_status(session, call_id, CallStatus.processing.value)

    transcriber = get_transcriber(call.fixture)
    result = transcriber.transcribe(
        call.audio_uri, call.channels, language=call.language_hint
    )

    tid = session.execute(
        text(
            """
            INSERT INTO transcripts
                (call_id, engine, language, code_switch_ratio, wer_estimate, text,
                 created_at, updated_at)
            VALUES (:cid, :engine, :lang, :csr, :wer, :text, now(), now())
            RETURNING id
            """
        ),
        {
            "cid": call_id, "engine": result.engine, "lang": result.language,
            "csr": result.code_switch_ratio, "wer": result.wer_estimate,
            "text": result.text,
        },
    ).scalar_one()

    for seg in result.segments:
        session.execute(
            text(
                """
                INSERT INTO segments
                    (transcript_id, idx, speaker, start_s, end_s, text)
                VALUES (:tid, :idx, :spk, :st, :en, :txt)
                """
            ),
            {
                "tid": tid, "idx": seg.idx, "spk": seg.speaker,
                "st": seg.start_s, "en": seg.end_s, "txt": seg.text,
            },
        )
    log.info("call %s transcribed: %d segments (%s)", call_id,
             len(result.segments), result.engine)
