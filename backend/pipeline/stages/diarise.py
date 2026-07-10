"""Stage 2: DIARISE — assign advisor/customer to each segment."""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from pipeline.stages.base import load_call, load_tx_segments, merge_raw_metadata
from transcription.diarize import diarise as diarise_segments

log = logging.getLogger("callsense.stage.diarise")


def run(session: Session, call_id: int) -> None:
    call = load_call(session, call_id)
    segments = load_tx_segments(session, call_id)
    if not segments:
        log.warning("no segments for call %s; skipping diarise", call_id)
        return

    labelled, confidence = diarise_segments(call.audio_uri, call.channels, segments)

    for seg in labelled:
        session.execute(
            text(
                """
                UPDATE segments s SET speaker = :spk
                FROM transcripts t
                WHERE s.transcript_id = t.id AND t.call_id = :cid AND s.idx = :idx
                """
            ),
            {"spk": seg.speaker, "cid": call_id, "idx": seg.idx},
        )

    # Persist confidence so the call page can show a "low diarisation confidence"
    # banner when we fell back to turn-based labelling.
    merge_raw_metadata(session, call_id, {"diarisation_confidence": confidence})
    log.info("call %s diarised (confidence %.2f)", call_id, confidence)
