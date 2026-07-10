"""FasterWhisperTranscriber — local, multilingual (Hinglish), CPU-friendly.

int8 quantisation keeps it cheap; VAD filtering skips silence/hold-music so
Whisper doesn't waste time or hallucinate. The model is lazily loaded on first
use (and downloaded once) so importing this module is free in MOCK_MODE.
"""

from __future__ import annotations

import math

from transcription.base import Transcriber, TranscriptResult, TxSegment
from transcription.textutils import estimate_code_switch


class FasterWhisperTranscriber(Transcriber):
    def __init__(self, model_size: str = "small", compute_type: str = "int8"):
        self.model_size = model_size
        self.compute_type = compute_type
        self._model = None

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel  # lazy: heavy import

            self._model = WhisperModel(
                self.model_size, device="cpu", compute_type=self.compute_type
            )
        return self._model

    def transcribe(self, audio_uri: str, channels: int | None = None) -> TranscriptResult:
        model = self._load()
        raw_segments, info = model.transcribe(
            audio_uri, vad_filter=True, beam_size=5
        )
        segments: list[TxSegment] = []
        logprobs: list[float] = []
        for i, s in enumerate(raw_segments):
            segments.append(
                TxSegment(idx=i, start_s=float(s.start), end_s=float(s.end),
                          text=s.text.strip())
            )
            if s.avg_logprob is not None:
                logprobs.append(s.avg_logprob)

        text = " ".join(seg.text for seg in segments)
        return TranscriptResult(
            engine=f"faster-whisper:{self.model_size}",
            language=info.language,
            text=text,
            segments=segments,
            code_switch_ratio=estimate_code_switch(text),
            wer_estimate=_wer_estimate(logprobs),
        )


def _wer_estimate(logprobs: list[float]) -> float | None:
    """Rough transcript-quality proxy from mean token logprob (no reference
    available in production). Maps avg_logprob -> ~0 (clean) .. ~1 (noisy)."""
    if not logprobs:
        return None
    mean = sum(logprobs) / len(logprobs)
    return round(min(1.0, max(0.0, 1.0 - math.exp(mean))), 3)
