"""Acoustic (voice-based) mono diarisation — numpy only, no gated models.

For mono recordings the channel-split trick is unavailable, and alternating
speakers on pauses mislabels anyone who talks twice in a row. This module gives
each transcript segment a small *voice fingerprint* and clusters them into two
speakers:

  fingerprint = mean log-mel spectral envelope (40 bands)  -> timbre/vocal tract
              + median fundamental frequency (autocorr)    -> pitch

  cluster     = 2-means on z-scored features (cosine-ish via z-scores)
  advisor     = the cluster containing the call opener (advisors open calls)
  confidence  = between-centroid distance vs within-cluster spread, squashed

If the two clusters are not genuinely separated (same-voice recording, music,
heavy noise), we return None and the caller keeps the turn-based fallback with
low confidence — degrade honestly, never pretend.

pyannote (HF-gated) remains the documented production upgrade; this exists so a
demo never depends on a gated model download.
"""

from __future__ import annotations

import logging

import numpy as np

from transcription.base import TxSegment

log = logging.getLogger("callsense.acoustic")

# Below this separation score the clusters are considered indistinct.
MIN_SEPARATION = 1.15
# Segments shorter than this contribute unreliable fingerprints.
MIN_SEG_S = 0.4


# --------------------------------------------------------------------------
# Feature extraction
# --------------------------------------------------------------------------
def _mel_filterbank(n_fft: int, sr: int, n_mels: int = 40) -> np.ndarray:
    """Triangular mel filterbank (librosa-style, slaney-ish, numpy only)."""
    f_min, f_max = 50.0, min(4000.0, sr / 2)  # telephone band
    mel = lambda f: 2595.0 * np.log10(1.0 + f / 700.0)  # noqa: E731
    inv = lambda m: 700.0 * (10.0 ** (m / 2595.0) - 1.0)  # noqa: E731
    pts = inv(np.linspace(mel(f_min), mel(f_max), n_mels + 2))
    bins = np.floor((n_fft + 1) * pts / sr).astype(int)
    fb = np.zeros((n_mels, n_fft // 2 + 1))
    for i in range(n_mels):
        lo, mid, hi = bins[i], bins[i + 1], bins[i + 2]
        if mid == lo:
            mid += 1
        if hi <= mid:
            hi = mid + 1
        fb[i, lo:mid] = np.linspace(0, 1, mid - lo, endpoint=False)
        fb[i, mid:hi] = np.linspace(1, 0, hi - mid, endpoint=False)
    return fb


def _frames(x: np.ndarray, frame: int, hop: int) -> np.ndarray:
    if len(x) < frame:
        return np.empty((0, frame))
    n = 1 + (len(x) - frame) // hop
    idx = np.arange(frame)[None, :] + hop * np.arange(n)[:, None]
    return x[idx]


def _pitch_hz(x: np.ndarray, sr: int) -> float:
    """Median F0 via short-frame autocorrelation (80-350 Hz search band)."""
    frame, hop = int(0.04 * sr), int(0.02 * sr)
    lo, hi = int(sr / 350), int(sr / 80)
    pitches = []
    for fr in _frames(x, frame, hop):
        fr = fr - fr.mean()
        rms = np.sqrt((fr**2).mean())
        if rms < 1e-4:  # silence
            continue
        ac = np.correlate(fr, fr, mode="full")[len(fr) - 1 :]
        if hi >= len(ac):
            continue
        seg = ac[lo:hi]
        peak = int(np.argmax(seg)) + lo
        if ac[peak] > 0.3 * ac[0]:  # voiced enough
            pitches.append(sr / peak)
    return float(np.median(pitches)) if pitches else 0.0


def _fingerprint(x: np.ndarray, sr: int, fb: np.ndarray, n_fft: int) -> np.ndarray | None:
    """40-dim mean log-mel envelope + pitch, or None if the crop is unusable."""
    frame, hop = n_fft, n_fft // 2
    fr = _frames(x, frame, hop)
    if fr.shape[0] < 3:
        return None
    fr = fr * np.hanning(frame)
    power = np.abs(np.fft.rfft(fr, axis=1)) ** 2
    energy = power.sum(axis=1)
    voiced = energy > max(1e-10, np.percentile(energy, 30))  # drop silent frames
    if voiced.sum() < 3:
        return None
    mel = np.log10(power[voiced] @ fb.T + 1e-10).mean(axis=0)
    return np.append(mel, _pitch_hz(x, sr))


# --------------------------------------------------------------------------
# Clustering
# --------------------------------------------------------------------------
def _two_means(feats: np.ndarray, iters: int = 50) -> tuple[np.ndarray, float]:
    """Tiny deterministic 2-means. Returns (labels, separation score)."""
    # Seed with the two most mutually distant points (deterministic).
    d = np.linalg.norm(feats[:, None] - feats[None, :], axis=2)
    i, j = np.unravel_index(int(np.argmax(d)), d.shape)
    c = np.stack([feats[i], feats[j]])
    labels = np.zeros(len(feats), dtype=int)
    for _ in range(iters):
        dist = np.linalg.norm(feats[:, None] - c[None, :], axis=2)
        new = dist.argmin(axis=1)
        if (new == labels).all() and _ > 0:
            break
        labels = new
        for k in (0, 1):
            if (labels == k).any():
                c[k] = feats[labels == k].mean(axis=0)
    if len(set(labels)) < 2:
        return labels, 0.0
    within = np.mean(
        [np.linalg.norm(feats[labels == k] - c[k], axis=1).mean() for k in (0, 1)
         if (labels == k).any()]
    )
    between = np.linalg.norm(c[0] - c[1])
    return labels, float(between / (within + 1e-9))


# --------------------------------------------------------------------------
# Public entrypoint
# --------------------------------------------------------------------------
def acoustic_diarise(
    audio_uri: str, segments: list[TxSegment]
) -> tuple[list[TxSegment], float] | None:
    """Voice-cluster mono segments into advisor/customer. None => not separable."""
    try:
        import soundfile as sf

        # float32 halves memory — an 11-minute 44.1kHz file is ~250MB instead
        # of ~500MB, which matters alongside the Whisper model in one worker.
        data, sr = sf.read(audio_uri, always_2d=True, dtype="float32")
    except Exception as exc:  # noqa: BLE001
        log.warning("acoustic diarise: cannot read audio (%s)", exc)
        return None

    mono = data.mean(axis=1, dtype=np.float32)
    del data
    n_fft = 512 if sr <= 16000 else 1024
    fb = _mel_filterbank(n_fft, sr)

    feats, owners = [], []
    for seg in segments:
        if seg.end_s - seg.start_s < MIN_SEG_S:
            continue
        a, b = int(seg.start_s * sr), int(seg.end_s * sr)
        fp = _fingerprint(mono[max(0, a) : min(len(mono), b)], sr, fb, n_fft)
        if fp is not None:
            feats.append(fp)
            owners.append(seg.idx)

    if len(feats) < 4:  # too little voiced material to cluster
        return None

    z = np.asarray(feats)
    z = (z - z.mean(axis=0)) / (z.std(axis=0) + 1e-9)
    labels, separation = _two_means(z)
    if separation < MIN_SEPARATION:
        log.info("acoustic diarise: clusters not separable (%.2f)", separation)
        return None

    by_idx = dict(zip(owners, labels))
    # The advisor opens the call: whichever cluster owns the first fingerprinted
    # segment is the advisor.
    advisor_cluster = by_idx[owners[0]]
    last = None
    for seg in segments:
        if seg.idx in by_idx:
            seg.speaker = "advisor" if by_idx[seg.idx] == advisor_cluster else "customer"
            last = seg.speaker
        else:
            # Un-fingerprintable slivers inherit the neighbouring speaker.
            seg.speaker = last or "unknown"

    confidence = round(float(min(0.95, 0.5 + separation / 8.0)), 3)
    log.info(
        "acoustic diarise: %d segments clustered (separation %.2f, conf %.2f)",
        len(segments), separation, confidence,
    )
    return segments, confidence
