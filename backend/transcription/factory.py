"""Transcriber factory — MockTranscriber in MOCK_MODE, else faster-whisper."""

from __future__ import annotations

from app.config import get_settings
from transcription.base import Transcriber


def get_transcriber(fixture: str | None = None) -> Transcriber:
    s = get_settings()
    if s.mock_mode:
        from transcription.mock import MockTranscriber

        return MockTranscriber(fixture)
    from transcription.faster_whisper_tx import FasterWhisperTranscriber

    return FasterWhisperTranscriber(s.whisper_model, s.whisper_compute_type)
