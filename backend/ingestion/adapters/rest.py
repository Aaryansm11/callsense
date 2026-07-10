"""RestAdapter — webhook/upload source (push).

The upload endpoint persists the bytes to the audio store and calls `build(...)`.
`fetch_new` returns [] because REST is push-based, not polled.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from ingestion.adapters.base import SourceAdapter
from ingestion.envelope import CallEnvelope, derive_idempotency_key


class RestAdapter(SourceAdapter):
    source_name = "rest"

    def __init__(self, store_dir: str):
        self.store_dir = Path(store_dir)

    def fetch_new(self) -> list[CallEnvelope]:
        return []

    def build(
        self,
        *,
        filename: str,
        content: bytes,
        advisor_external_id: str | None = None,
        org_id: int | None = 1,
        customer_ref: str | None = None,
        called_at: datetime | None = None,
        language_hint: str | None = None,
        extra: dict | None = None,
    ) -> CallEnvelope:
        self.store_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(filename).suffix or ".wav"
        dest = self.store_dir / f"{uuid.uuid4().hex}{suffix}"
        dest.write_bytes(content)
        return CallEnvelope(
            source=self.source_name,
            idempotency_key=derive_idempotency_key(content, self.source_name),
            audio_uri=str(dest.resolve()),
            advisor_external_id=advisor_external_id,
            org_id=org_id,
            source_call_id=Path(filename).stem,
            customer_ref=customer_ref,
            called_at=called_at,
            language_hint=language_hint,
            raw_metadata={"original_filename": filename, **(extra or {})},
        )
