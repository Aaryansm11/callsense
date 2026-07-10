"""FolderAdapter — watch a directory for audio files (polling source).

Metadata comes from an optional sidecar `<file>.json` next to the audio
(advisor_external_id, called_at, customer_ref, ...); absent that, the filename
stem becomes the source_call_id and the advisor is left unresolved. Dedup is
handled downstream by the idempotency key, so re-scanning the same file is safe.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from ingestion.adapters.base import SourceAdapter
from ingestion.envelope import CallEnvelope, derive_idempotency_key

AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".opus"}


class FolderAdapter(SourceAdapter):
    source_name = "folder"

    def __init__(self, inbox: str, default_org_id: int | None = 1):
        self.inbox = Path(inbox)
        self.default_org_id = default_org_id

    def fetch_new(self) -> list[CallEnvelope]:
        if not self.inbox.exists():
            return []
        return [
            self.build(p)
            for p in sorted(self.inbox.iterdir())
            if p.suffix.lower() in AUDIO_EXTS
        ]

    def build(self, path: Path) -> CallEnvelope:
        meta = self._sidecar(path)
        audio_bytes = path.read_bytes()
        return CallEnvelope(
            source=self.source_name,
            idempotency_key=derive_idempotency_key(audio_bytes, self.source_name),
            audio_uri=str(path.resolve()),
            advisor_external_id=meta.get("advisor_external_id"),
            org_id=meta.get("org_id", self.default_org_id),
            source_call_id=meta.get("source_call_id", path.stem),
            customer_ref=meta.get("customer_ref"),
            language_hint=meta.get("language_hint"),
            called_at=_parse_dt(meta.get("called_at")),
            raw_metadata=meta,
        )

    @staticmethod
    def _sidecar(path: Path) -> dict:
        side = path.with_suffix(path.suffix + ".json")
        if side.exists():
            try:
                return json.loads(side.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {}
        return {}


def _parse_dt(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None
