"""Quote-verification gate (rubric §2.9, §6.3.2) — the anti-hallucination core.

Every flag/evidence quote from the model is fuzzy-matched (normalised, sliding
window, difflib ratio >= 0.85) against the actual transcript segments. A quote
that doesn't match is dropped and logged — the model cannot assert without
citing, and can't cite something that isn't there. Timestamps are DERIVED from
the matched segment (the model never does arithmetic).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from transcription.base import TxSegment

DEFAULT_THRESHOLD = 0.85
# Unicode-aware: keep word characters from ANY script (real Whisper renders
# Hinglish in Devanagari — an ASCII-only normaliser would empty those quotes
# and silently drop every valid flag). \w matches Devanagari etc. by default.
_NORM = re.compile(r"[^\w\s]+", re.UNICODE)
_WS = re.compile(r"\s+")


def _normalise(s: str) -> str:
    return _WS.sub(" ", _NORM.sub(" ", s.lower())).strip()


@dataclass
class QuoteMatch:
    found: bool
    ratio: float
    segment_idx: int | None
    start_s: float | None
    end_s: float | None


def verify_quote(
    quote: str, segments: list[TxSegment], threshold: float = DEFAULT_THRESHOLD
) -> QuoteMatch:
    q = _normalise(quote)
    qwords = q.split()
    if not qwords:
        return QuoteMatch(False, 0.0, None, None, None)

    best_ratio, best_seg = 0.0, None
    for seg in segments:
        swords = _normalise(seg.text).split()
        if not swords:
            continue
        if len(swords) <= len(qwords):
            r = SequenceMatcher(None, q, " ".join(swords)).ratio()
            if r > best_ratio:
                best_ratio, best_seg = r, seg
        else:
            window = len(qwords)
            for i in range(len(swords) - window + 1):
                cand = " ".join(swords[i : i + window])
                r = SequenceMatcher(None, q, cand).ratio()
                if r > best_ratio:
                    best_ratio, best_seg = r, seg

    found = best_ratio >= threshold
    return QuoteMatch(
        found=found,
        ratio=round(best_ratio, 3),
        segment_idx=best_seg.idx if best_seg else None,
        start_s=best_seg.start_s if best_seg else None,
        end_s=best_seg.end_s if best_seg else None,
    )
