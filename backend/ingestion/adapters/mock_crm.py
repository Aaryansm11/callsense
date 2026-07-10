"""MockCrmAdapter — a canned CRM/dialer poll that proves source-agnosticism.

It maps a vendor-shaped payload (agent_ref, recording_path, lead_phone, ...) onto
the same CallEnvelope the folder and REST sources produce. Swapping this for a
real Exotel/Knowlarity adapter is one file; the pipeline never knows.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ingestion.adapters.base import SourceAdapter
from ingestion.envelope import CallEnvelope, derive_idempotency_key


class MockCrmAdapter(SourceAdapter):
    source_name = "crm"

    def __init__(self, records: list[dict] | None = None):
        # Each record mimics a dialer's export row. `recording_path` points at a
        # fixture audio file on disk.
        self.records = records or []

    def fetch_new(self) -> list[CallEnvelope]:
        envelopes: list[CallEnvelope] = []
        for rec in self.records:
            path = Path(rec["recording_path"])
            if not path.exists():
                continue
            audio_bytes = path.read_bytes()
            envelopes.append(
                CallEnvelope(
                    source=self.source_name,
                    idempotency_key=derive_idempotency_key(audio_bytes, self.source_name),
                    audio_uri=str(path.resolve()),
                    advisor_external_id=rec.get("agent_ref"),
                    org_id=rec.get("org_id", 1),
                    source_call_id=rec.get("call_uuid"),
                    customer_ref=rec.get("lead_phone"),
                    language_hint=rec.get("lang"),
                    called_at=_parse(rec.get("started_at")),
                    raw_metadata=rec,  # preserve the whole vendor row
                )
            )
        return envelopes


def _parse(value) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value)) if value else None
    except ValueError:
        return None
