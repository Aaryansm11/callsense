"""Diarisation: who spoke when + advisor/customer roles (rubric §1.9, §6.4).

Strategy, cheapest-correct first:
1. If segments are already speaker-labelled (mock fixture, or a diarising cloud
   STT), pass them through.
2. Stereo call recordings put advisor on one channel, customer on the other →
   per-segment channel energy assigns the speaker with zero ML (left=advisor).
3. Mono → ACOUSTIC clustering: per-segment voice fingerprints (spectral envelope
   + pitch) clustered into two speakers; advisor = call opener. Voice-based, not
   gap-based.
4. Only if the voices aren't acoustically separable → turn-based fallback
   (alternate speakers) with low confidence, so the call page shows a "low
   diarisation confidence" banner. We still score what's scoreable rather than
   going silent. pyannote (HF token) is the documented production upgrade.
"""

from __future__ import annotations

import logging

from transcription.acoustic import acoustic_diarise
from transcription.base import TxSegment

log = logging.getLogger("callsense.diarize")

# Below this L/R energy separation a "stereo" file is effectively mono.
_STEREO_SEPARATION_MIN = 0.15


def diarise(
    audio_uri: str, channels: int | None, segments: list[TxSegment]
) -> tuple[list[TxSegment], float]:
    if segments and all(s.speaker != "unknown" for s in segments):
        return segments, 1.0
    if channels and channels >= 2:
        result = _channel_split(audio_uri, segments)
        if result is not None:
            return result
    # Mono (or unsplittable stereo): cluster by VOICE before giving up.
    acoustic = acoustic_diarise(audio_uri, segments)
    if acoustic is not None:
        return acoustic
    return _turn_fallback(segments), 0.5


def _channel_split(
    audio_uri: str, segments: list[TxSegment]
) -> tuple[list[TxSegment], float] | None:
    try:
        import numpy as np
        import soundfile as sf

        data, sr = sf.read(audio_uri, always_2d=True)
    except Exception as exc:  # noqa: BLE001 - any decode/read issue -> fallback
        log.warning("channel-split unavailable (%s); using turn fallback", exc)
        return None

    if data.shape[1] < 2:
        return None

    left, right = data[:, 0], data[:, 1]
    separations: list[float] = []
    for seg in segments:
        a, b = int(seg.start_s * sr), int(seg.end_s * sr)
        a, b = max(0, a), min(len(data), b)
        if b <= a:
            seg.speaker = "unknown"
            continue
        l_rms = float(np.sqrt(np.mean(left[a:b] ** 2)) + 1e-9)
        r_rms = float(np.sqrt(np.mean(right[a:b] ** 2)) + 1e-9)
        total = l_rms + r_rms
        separations.append(abs(l_rms - r_rms) / total)
        seg.speaker = "advisor" if l_rms >= r_rms else "customer"  # left = advisor

    mean_sep = sum(separations) / len(separations) if separations else 0.0
    if mean_sep < _STEREO_SEPARATION_MIN:
        # Channels barely differ -> effectively mono; let the caller try the
        # acoustic (voice) path before any naive fallback.
        return None

    # Sanity check the result: a genuinely channel-separated two-party call
    # must yield BOTH speakers. If one label swallowed (nearly) everything,
    # the "separation" was just a constant mixing imbalance (common in
    # music-style/generated stereo files where both voices sit on both
    # channels) -> not channel-separated; let voice clustering decide.
    labelled = [s for s in segments if s.speaker in ("advisor", "customer")]
    minority = min(
        sum(1 for s in labelled if s.speaker == "advisor"),
        sum(1 for s in labelled if s.speaker == "customer"),
    )
    if len(labelled) >= 4 and minority < max(2, len(labelled) // 10):
        log.info(
            "channel-split produced a one-sided result (%d/%d minority); "
            "treating as mixed stereo and falling back to voice clustering",
            minority, len(labelled),
        )
        return None

    return segments, round(min(1.0, 0.6 + mean_sep), 3)


def _turn_fallback(segments: list[TxSegment]) -> list[TxSegment]:
    """Alternate speakers on each turn, starting with the advisor."""
    speaker = "advisor"
    for i, seg in enumerate(segments):
        seg.speaker = speaker
        speaker = "customer" if speaker == "advisor" else "advisor"
    return segments
