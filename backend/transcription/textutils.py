"""Small text helpers used by transcription."""

from __future__ import annotations

import re

# A tiny English lexicon; tokens outside it are treated as (romanised) non-English
# for a crude code-switch estimate. Good enough to store a monitoring signal.
_COMMON_EN = {
    "the", "a", "an", "is", "are", "am", "and", "or", "but", "for", "to", "of",
    "in", "on", "at", "it", "you", "i", "we", "they", "he", "she", "sir", "maam",
    "hello", "yes", "no", "ok", "okay", "course", "fees", "data", "science",
    "placement", "job", "trial", "emi", "otp", "card", "number", "python", "sql",
    "support", "program", "great", "perfect", "company", "student", "analytics",
}
_WORD = re.compile(r"[a-zA-Z]+")


def estimate_code_switch(text: str) -> float:
    tokens = _WORD.findall(text.lower())
    if not tokens:
        return 0.0
    non_en = sum(1 for t in tokens if t not in _COMMON_EN)
    return round(non_en / len(tokens), 3)
