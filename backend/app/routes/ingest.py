"""POST /ingest/upload — REST source. Persists audio, ingests, enqueues.

`process=true` drains the queue inline so a single-process demo shows results
immediately (in production the separate worker service does this)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.config import get_settings
from app.deps import get_queue
from app.schemas import IngestResponse
from db.session import get_db
from ingestion.adapters.rest import RestAdapter
from ingestion.service import ingest
from pipeline import worker

router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("/upload", response_model=IngestResponse)
async def upload(
    file: UploadFile = File(...),
    advisor_external_id: str | None = Form(default=None),
    org_id: int | None = Form(default=1),
    fixture: str | None = Form(default=None),
    process: bool = Form(default=False),
    db: Session = Depends(get_db),
    queue=Depends(get_queue),
) -> IngestResponse:
    settings = get_settings()
    content = await file.read()
    adapter = RestAdapter(settings.audio_storage_dir)
    # A fixture name only means something in MOCK_MODE; in real mode the actual
    # audio is transcribed (faster-whisper) and judged (LLM) — ignore it so a
    # stale UI param can't mislabel a real call.
    fixture = fixture if settings.mock_mode else None
    env = adapter.build(
        filename=file.filename or "upload.wav",
        content=content,
        advisor_external_id=advisor_external_id,
        org_id=org_id,
        extra={"fixture": fixture} if fixture else None,
    )
    result = ingest(db, env, queue)
    db.commit()

    # Inline drain is instant with mocks; with real Whisper+LLM it would block
    # this request for minutes — the worker service owns processing there.
    processed = False
    if process and result.created and settings.mock_mode:
        worker.run_until_idle(queue)
        processed = True

    return IngestResponse(
        accepted=result.accepted, created=result.created,
        call_id=result.call_id, reason=result.reason, processed_inline=processed,
    )
