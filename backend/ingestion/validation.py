"""Ingest-time audio validation gate (rubric §6.4).

ffprobe answers: is this actually audio, is duration > 0, how many channels?
A renamed .txt or a zero-length file is rejected with a reason (into the audit
log by the caller) and never enters the pipeline.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass


class AudioValidationError(Exception):
    """Raised when a file is not usable audio; message is the rejection reason."""


@dataclass
class AudioInfo:
    channels: int
    duration_s: float
    codec: str
    sample_rate: int | None


def _ffprobe_path() -> str:
    exe = shutil.which("ffprobe")
    if not exe:
        raise AudioValidationError(
            "ffprobe not found on PATH (install ffmpeg to enable validation)"
        )
    return exe


def probe_audio(path: str) -> AudioInfo:
    """Return AudioInfo or raise AudioValidationError with a human reason."""
    try:
        out = subprocess.run(
            [
                _ffprobe_path(),
                "-v", "error",
                "-show_streams",
                "-show_format",
                "-of", "json",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired as exc:  # pragma: no cover - defensive
        raise AudioValidationError("ffprobe timed out") from exc

    if out.returncode != 0:
        raise AudioValidationError(
            f"ffprobe rejected the file: {out.stderr.strip() or 'not decodable'}"
        )

    data = json.loads(out.stdout or "{}")
    audio_streams = [
        s for s in data.get("streams", []) if s.get("codec_type") == "audio"
    ]
    if not audio_streams:
        raise AudioValidationError("no audio stream found")

    stream = audio_streams[0]
    duration = _first_duration(stream, data.get("format", {}))
    if duration is None or duration <= 0:
        raise AudioValidationError("audio has zero/unknown duration")

    return AudioInfo(
        channels=int(stream.get("channels", 0)) or 1,
        duration_s=float(duration),
        codec=str(stream.get("codec_name", "unknown")),
        sample_rate=int(stream["sample_rate"]) if stream.get("sample_rate") else None,
    )


def _first_duration(stream: dict, fmt: dict) -> float | None:
    for src in (stream.get("duration"), fmt.get("duration")):
        try:
            if src is not None:
                return float(src)
        except (TypeError, ValueError):
            continue
    return None
