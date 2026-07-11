"""Quote-verification gate unit tests (rubric §9.1, §2.9)."""

from analysis.verify import verify_quote
from transcription.base import TxSegment


def _segments():
    return [
        TxSegment(0, 0.0, 4.0, "Sir is course ke baad placement 100% guaranteed hai"),
        TxSegment(1, 4.0, 7.0, "Fees pachaas hazaar hai"),
    ]


def test_exact_quote_found_with_timestamp():
    m = verify_quote("placement 100% guaranteed hai", _segments())
    assert m.found and m.start_s == 0.0 and m.ratio >= 0.85


def test_stt_noisy_quote_still_matches():
    # Whisper-style typos should still pass the fuzzy threshold.
    m = verify_quote("placement 100% guranteed hai", _segments())
    assert m.found


def test_absent_quote_is_dropped():
    # Below-threshold match => flag is dropped (found is what the gate acts on).
    m = verify_quote("hum aapko free laptop denge", _segments())
    assert not m.found and m.ratio < 0.85


def test_empty_quote_not_found():
    assert not verify_quote("", _segments()).found


def test_devanagari_quote_matches():
    # Real Whisper renders Hinglish in Devanagari; the gate must still verify.
    segs = [TxSegment(0, 0.0, 5.0, "सर इस प्रोग्राम के बाद वेट लोस बिलकुल गारेंटीड है")]
    m = verify_quote("वेट लोस बिलकुल गारेंटीड है", segs)
    assert m.found and m.start_s == 0.0


def test_devanagari_absent_quote_dropped():
    segs = [TxSegment(0, 0.0, 5.0, "सर इस प्रोग्राम के बाद वेट लोस बिलकुल गारेंटीड है")]
    assert not verify_quote("हम आपको मुफ्त लैपटॉप देंगे", segs).found
