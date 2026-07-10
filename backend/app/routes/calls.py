"""Calls: recent list + full detail (transcript + segments + scores + flags)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from db.session import get_db

router = APIRouter(tags=["calls"])

_MEDIA = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".m4a": "audio/mp4",
          ".ogg": "audio/ogg", ".flac": "audio/flac", ".opus": "audio/ogg"}


@router.get("/calls/{call_id}/audio")
def call_audio(call_id: int, db: Session = Depends(get_db)) -> FileResponse:
    row = db.execute(
        text("SELECT audio_uri FROM calls WHERE id = :id"), {"id": call_id}
    ).first()
    if row is None or not row.audio_uri:
        raise HTTPException(status_code=404, detail="no audio for call")
    path = Path(row.audio_uri)
    if not path.exists():
        raise HTTPException(status_code=404, detail="audio file missing on disk")
    return FileResponse(str(path), media_type=_MEDIA.get(path.suffix.lower(), "audio/wav"))


@router.get("/calls")
def list_calls(limit: int = 50, db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(
        text(
            """
            SELECT c.id, c.status, c.called_at, c.source, c.duration_s,
                   a.name AS advisor_name, a.id AS advisor_id,
                   cs.composite, cs.compliance_capped,
                   (SELECT count(*) FROM flags f WHERE f.call_id = c.id) AS flag_count,
                   (SELECT count(*) FROM flags f WHERE f.call_id = c.id
                        AND f.severity = 'critical') AS critical_count
            FROM calls c
            LEFT JOIN advisors a ON a.id = c.advisor_id
            LEFT JOIN call_scores cs ON cs.call_id = c.id
            ORDER BY c.created_at DESC
            LIMIT :lim
            """
        ),
        {"lim": limit},
    ).mappings().all()
    return [dict(r) for r in rows]


@router.get("/calls/{call_id}")
def call_detail(call_id: int, db: Session = Depends(get_db)) -> dict:
    call = db.execute(
        text(
            """
            SELECT c.id, c.status, c.source, c.called_at, c.duration_s, c.channels,
                   c.language_hint, c.audio_uri, c.raw_metadata,
                   a.id AS advisor_id, a.name AS advisor_name, t.name AS team_name,
                   cs.composite, cs.compliance_capped, cs.rubric_version
            FROM calls c
            LEFT JOIN advisors a ON a.id = c.advisor_id
            LEFT JOIN teams t ON t.id = a.team_id
            LEFT JOIN call_scores cs ON cs.call_id = c.id
            WHERE c.id = :id
            """
        ),
        {"id": call_id},
    ).mappings().first()
    if call is None:
        raise HTTPException(status_code=404, detail="call not found")

    transcript = db.execute(
        text(
            "SELECT engine, language, code_switch_ratio, wer_estimate "
            "FROM transcripts WHERE call_id = :id"
        ),
        {"id": call_id},
    ).mappings().first()

    segments = db.execute(
        text(
            """
            SELECT s.idx, s.speaker, s.start_s, s.end_s,
                   COALESCE(s.redacted_text, s.text) AS text
            FROM segments s JOIN transcripts t ON t.id = s.transcript_id
            WHERE t.call_id = :id ORDER BY s.idx
            """
        ),
        {"id": call_id},
    ).mappings().all()

    scores = db.execute(
        text(
            "SELECT dimension, raw_score, weight, evidence_quote, evidence_start_s, "
            "model, prompt_hash FROM scores WHERE call_id = :id ORDER BY id"
        ),
        {"id": call_id},
    ).mappings().all()

    flags = db.execute(
        text(
            "SELECT id, tag, severity, start_s, end_s, quote, reason, confidence, "
            "state FROM flags WHERE call_id = :id ORDER BY start_s NULLS LAST, id"
        ),
        {"id": call_id},
    ).mappings().all()

    return {
        "call": dict(call),
        "transcript": dict(transcript) if transcript else None,
        "segments": [dict(s) for s in segments],
        "scores": [dict(s) for s in scores],
        "flags": [dict(f) for f in flags],
    }
