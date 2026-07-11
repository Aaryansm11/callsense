"""Acoustic (voice-based) mono diarisation tests.

Two synthetic "voices" — different fundamental pitch AND different spectral
envelopes — alternating in one mono file. The clusterer must separate them by
voice, including two consecutive turns by the same speaker (the case the naive
turn-alternation fallback always gets wrong).
"""

import numpy as np
import pytest
import soundfile as sf

from transcription.acoustic import acoustic_diarise
from transcription.base import TxSegment

SR = 16000


def _voice(f0: float, dur_s: float, brightness: float) -> np.ndarray:
    """A crude vowel-like voice: harmonic stack on f0 with an envelope knob."""
    t = np.arange(int(dur_s * SR)) / SR
    x = np.zeros_like(t)
    rng = np.random.default_rng(int(f0))
    for k in range(1, 12):
        amp = (1.0 / k) ** brightness
        x += amp * np.sin(2 * np.pi * f0 * k * t + rng.uniform(0, np.pi))
    # gentle amplitude modulation so frames aren't identical
    x *= 0.15 * (1.0 + 0.3 * np.sin(2 * np.pi * 3.0 * t))
    return x.astype(np.float32)


@pytest.fixture()
def two_voice_call(tmp_path):
    """Mono file: A(2s) B(2s) A(2s) A(2s) B(2s) — note A speaks twice in a row."""
    gap = np.zeros(int(0.3 * SR), dtype=np.float32)
    # A: low pitch, dark envelope. B: high pitch, bright envelope.
    a = lambda: _voice(115.0, 2.0, brightness=1.6)  # noqa: E731
    b = lambda: _voice(230.0, 2.0, brightness=0.8)  # noqa: E731
    order = [("A", a), ("B", b), ("A", a), ("A", a), ("B", b)]
    samples, segments, pos = [], [], 0.0
    for i, (who, mk) in enumerate(order):
        clip = mk()
        samples += [clip, gap]
        segments.append(
            (who, TxSegment(idx=i, start_s=pos, end_s=pos + 2.0, text=f"turn {i}"))
        )
        pos += 2.0 + 0.3
    path = tmp_path / "two_voices.wav"
    sf.write(str(path), np.concatenate(samples), SR)
    return path, segments


def test_clusters_by_voice_not_by_turn_order(two_voice_call):
    path, labelled = two_voice_call
    segments = [seg for _, seg in labelled]
    result = acoustic_diarise(str(path), segments)
    assert result is not None, "distinct voices must be separable"
    out, confidence = result
    assert confidence > 0.5

    # Same physical voice => same label; first speaker is the advisor.
    roles = {who: set() for who, _ in labelled}
    for who, seg in labelled:
        roles[who].add(seg.speaker)
    assert roles["A"] == {"advisor"}, f"A got {roles['A']}"
    assert roles["B"] == {"customer"}, f"B got {roles['B']}"
    # The back-to-back A turns (idx 2 and 3) is what turn-alternation gets wrong.
    assert out[2].speaker == out[3].speaker == "advisor"


def test_single_voice_returns_none(tmp_path):
    """One voice throughout -> clusters not separable -> honest None."""
    gap = np.zeros(int(0.3 * SR), dtype=np.float32)
    clips, segments, pos = [], [], 0.0
    for i in range(5):
        clips += [_voice(140.0, 1.5, brightness=1.2), gap]
        segments.append(TxSegment(idx=i, start_s=pos, end_s=pos + 1.5, text=f"t{i}"))
        pos += 1.8
    path = tmp_path / "one_voice.wav"
    sf.write(str(path), np.concatenate(clips), SR)
    assert acoustic_diarise(str(path), segments) is None


def test_unreadable_audio_returns_none(tmp_path):
    path = tmp_path / "not_audio.wav"
    path.write_bytes(b"definitely not audio")
    segs = [TxSegment(idx=0, start_s=0.0, end_s=1.0, text="x")]
    assert acoustic_diarise(str(path), segs) is None


def test_biased_stereo_mix_falls_through_to_voice_clustering(tmp_path):
    """Regression: a stereo file with BOTH voices mixed into BOTH channels and a
    constant left-bias must NOT be treated as channel-separated (that labelled
    every segment 'advisor' in production). diarise() must detect the one-sided
    channel-split result and use voice clustering instead."""
    from transcription.diarize import diarise

    gap = np.zeros(int(0.3 * SR), dtype=np.float32)
    order = [(115.0, 1.6), (230.0, 0.8), (115.0, 1.6), (115.0, 1.6), (230.0, 0.8), (230.0, 0.8)]
    clips, segments, pos = [], [], 0.0
    for i, (f0, bright) in enumerate(order):
        clips += [_voice(f0, 2.0, brightness=bright), gap]
        segments.append(TxSegment(idx=i, start_s=pos, end_s=pos + 2.0, text=f"t{i}"))
        pos += 2.3
    mono = np.concatenate(clips)
    # Both voices on both channels; left is uniformly louder -> every segment
    # is "left-heavy", the trap for naive channel-splitting.
    stereo = np.stack([mono * 1.0, mono * 0.6], axis=1)
    path = tmp_path / "biased_stereo.wav"
    sf.write(str(path), stereo, SR)

    labelled, confidence = diarise(str(path), channels=2, segments=segments)
    speakers = {s.speaker for s in labelled}
    assert speakers == {"advisor", "customer"}, f"one-sided labels: {speakers}"
    # Same physical voice must share a label (clustered by voice, not channel).
    assert labelled[0].speaker == labelled[2].speaker == labelled[3].speaker
    assert labelled[1].speaker == labelled[4].speaker == labelled[5].speaker
