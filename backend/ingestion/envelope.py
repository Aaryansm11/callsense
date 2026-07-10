"""CallEnvelope — the single normalized shape every call takes on entry,
regardless of source (rubric §3.6). Everything downstream depends on this shape
only; `raw_metadata` preserves the untouched vendor payload for later re-mapping.
"""

from __future__ import annotations

import hashlib
from datetime import datetime

from pydantic import BaseModel, Field


def derive_idempotency_key(audio_bytes: bytes, source: str) -> str:
    """`sha256(audio_bytes) + source` — the double-delivery guard (rubric §5).

    Content-derived, so the same recording delivered twice (even under different
    filenames or from a retrying webhook) collides to one key.
    """
    digest = hashlib.sha256(audio_bytes).hexdigest()
    return f"{digest}:{source}"


class CallEnvelope(BaseModel):
    """Canonical ingestion payload. Adapters translate their source into this."""

    source: str  # folder | rest | crm
    idempotency_key: str
    audio_uri: str  # local path (demo) or URL (prod telephony export)

    # Resolved against advisors.external_ids at ingest; None -> advisor unknown.
    advisor_external_id: str | None = None
    # Fallback org when the advisor can't be resolved (demo convenience).
    org_id: int | None = None

    source_call_id: str | None = None
    customer_ref: str | None = None
    channels: int | None = None
    duration_s: float | None = None
    language_hint: str | None = None
    called_at: datetime | None = None
    raw_metadata: dict = Field(default_factory=dict)
