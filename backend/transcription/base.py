"""Transcriber interface + result types.

Cloud STT (Deepgram/Sarvam) is a config change: implement `transcribe` in a new
class. Timestamps are word/segment aligned so flags can anchor to seconds.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class TxSegment:
    idx: int
    start_s: float
    end_s: float
    text: str
    speaker: str = "unknown"  # advisor | customer | unknown (set by diarisation)


@dataclass
class TranscriptResult:
    engine: str
    language: str | None
    text: str
    segments: list[TxSegment] = field(default_factory=list)
    code_switch_ratio: float | None = None
    wer_estimate: float | None = None


class Transcriber(ABC):
    @abstractmethod
    def transcribe(self, audio_uri: str, channels: int | None = None) -> TranscriptResult:
        raise NotImplementedError
