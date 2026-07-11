"""MockTranscriber — returns a canned, speaker-labelled fixture transcript.

Lets the whole pipeline run with zero network / no model download. The fixture
is selected by name (from the call's raw_metadata); segments already carry
speaker labels, so the diarise stage passes them through.
"""

from __future__ import annotations

from fixtures import get_fixture
from transcription.base import Transcriber, TranscriptResult, TxSegment
from transcription.textutils import estimate_code_switch


class MockTranscriber(Transcriber):
    def __init__(self, fixture: str | None = None):
        self.fixture = fixture

    def transcribe(
        self,
        audio_uri: str,
        channels: int | None = None,
        language: str | None = None,
    ) -> TranscriptResult:
        fx = get_fixture(self.fixture)
        segments = [
            TxSegment(idx=i, start_s=s, end_s=e, text=t, speaker=sp)
            for i, (sp, s, e, t) in enumerate(fx["segments"])
        ]
        text = " ".join(seg.text for seg in segments)
        return TranscriptResult(
            engine="mock",
            language=fx["language"],
            text=text,
            segments=segments,
            code_switch_ratio=estimate_code_switch(text),
            wer_estimate=0.0,
        )
