"""Talk-ratio metric tests (deterministic, code-derived — rubric §6.2)."""

from analysis.metrics import TALK_RATIO_THRESHOLD, talk_ratio
from transcription.base import TxSegment


def _seg(idx, start, end, speaker):
    return TxSegment(idx=idx, start_s=start, end_s=end, text="x", speaker=speaker)


def test_balanced_conversation():
    segs = [_seg(0, 0, 10, "advisor"), _seg(1, 10, 20, "customer")]
    assert talk_ratio(segs) == 0.5


def test_domination_crosses_threshold():
    segs = [_seg(0, 0, 40, "advisor"), _seg(1, 40, 50, "customer")]
    ratio = talk_ratio(segs)
    assert ratio == 0.8 and ratio > TALK_RATIO_THRESHOLD


def test_unknown_speakers_yield_none():
    segs = [_seg(0, 0, 10, "unknown"), _seg(1, 10, 20, "unknown")]
    assert talk_ratio(segs) is None


def test_empty_yields_none():
    assert talk_ratio([]) is None
