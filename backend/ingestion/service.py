"""Ingest service: envelope -> validated, deduped call row -> first job enqueued.

Order of operations (rubric §3.8, §6.4):
1. ffprobe validation; rejects (corrupt/non-audio/zero-length) go to the audit
   log and never enter the pipeline.
2. Resolve the advisor from `advisors.external_ids ? agent_ref`; unknown agents
   still ingest (advisor_id NULL) so calls are never silently dropped.
3. Insert with `ON CONFLICT (idempotency_key) DO NOTHING` — double delivery
   dissolves into one row.
4. Enqueue the first stage (transcribe) only for a newly-created call.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from db.models import CallStatus, JobStage
from ingestion.envelope import CallEnvelope
from ingestion.validation import AudioValidationError, probe_audio
from pipeline.queue import JobQueue

log = logging.getLogger("callsense.ingest")

FIRST_STAGE = JobStage.transcribe.value


@dataclass
class IngestResult:
    accepted: bool
    created: bool
    call_id: int | None = None
    reason: str | None = None


def ingest(session: Session, env: CallEnvelope, queue: JobQueue) -> IngestResult:
    # 1. Validate audio.
    try:
        info = probe_audio(env.audio_uri)
    except AudioValidationError as exc:
        _audit(session, "ingest", "reject_call", env.source_call_id, str(exc), env)
        log.warning("rejected %s: %s", env.audio_uri, exc)
        return IngestResult(accepted=False, created=False, reason=str(exc))

    # 2. Resolve advisor (and its org) from external ids.
    advisor_id, org_id = _resolve_advisor(session, env)

    # 3. Idempotent insert.
    row = session.execute(
        text(
            """
            INSERT INTO calls
                (org_id, advisor_id, customer_ref, source, source_call_id,
                 idempotency_key, audio_uri, duration_s, called_at, channels,
                 language_hint, raw_metadata, status, created_at, updated_at)
            VALUES
                (:org_id, :advisor_id, :customer_ref, :source, :source_call_id,
                 :idem, :audio_uri, :duration_s, :called_at, :channels,
                 :language_hint, CAST(:raw AS jsonb), :status, now(), now())
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING id
            """
        ),
        {
            "org_id": org_id,
            "advisor_id": advisor_id,
            "customer_ref": env.customer_ref,
            "source": env.source,
            "source_call_id": env.source_call_id,
            "idem": env.idempotency_key,
            "audio_uri": env.audio_uri,
            "duration_s": env.duration_s or info.duration_s,
            "called_at": env.called_at,
            "channels": env.channels or info.channels,
            "language_hint": env.language_hint,
            "raw": json.dumps(env.raw_metadata),
            "status": CallStatus.received.value,
        },
    ).first()

    if row is None:
        existing = session.execute(
            text("SELECT id FROM calls WHERE idempotency_key = :k"),
            {"k": env.idempotency_key},
        ).first()
        log.info("duplicate delivery ignored (idempotency_key=%s)", env.idempotency_key)
        return IngestResult(
            accepted=True,
            created=False,
            call_id=existing.id if existing else None,
            reason="duplicate",
        )

    call_id = row.id
    # 4. Kick off the pipeline.
    queue.enqueue(session, call_id, FIRST_STAGE)
    _audit(session, "ingest", "create_call", str(call_id), "accepted", env)
    log.info("ingested call %s from %s (%d ch, %.1fs)", call_id, env.source,
             info.channels, info.duration_s)
    return IngestResult(accepted=True, created=True, call_id=call_id)


def _resolve_advisor(session: Session, env: CallEnvelope) -> tuple[int | None, int]:
    default_org = env.org_id or 1
    if not env.advisor_external_id:
        return None, default_org
    found = session.execute(
        text(
            """
            SELECT a.id AS advisor_id, t.org_id AS org_id
            FROM advisors a JOIN teams t ON t.id = a.team_id
            WHERE a.external_ids ? :ext
            LIMIT 1
            """
        ),
        {"ext": env.advisor_external_id},
    ).first()
    if found is None:
        return None, default_org
    return found.advisor_id, found.org_id


def _audit(
    session: Session, actor: str, action: str, entity_id: str | None,
    note: str, env: CallEnvelope,
) -> None:
    session.execute(
        text(
            """
            INSERT INTO audit_log (actor, action, entity, entity_id, after, at)
            VALUES (:actor, :action, 'call', :entity_id, CAST(:after AS jsonb), now())
            """
        ),
        {
            "actor": actor,
            "action": action,
            "entity_id": entity_id,
            "after": json.dumps(
                {"note": note, "source": env.source, "audio_uri": env.audio_uri}
            ),
        },
    )
