"""SourceAdapter — the one interface the pipeline speaks (rubric §3.5).

Each source (folder watch, REST upload, mock CRM poll, and later Exotel/Twilio)
implements `fetch_new` to emit canonical CallEnvelopes. The pipeline imports only
this interface, so a new telephony source is one new file with zero pipeline
changes — the assignment's "map a new source in without core code changes".
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ingestion.envelope import CallEnvelope


class SourceAdapter(ABC):
    source_name: str

    @abstractmethod
    def fetch_new(self) -> list[CallEnvelope]:
        """Return envelopes for any not-yet-seen calls. Pull sources scan;
        push sources (REST) return [] and build envelopes on request."""
        raise NotImplementedError
