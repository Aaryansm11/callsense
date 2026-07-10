"""Redaction unit tests (rubric §9.1)."""

from analysis.redaction import redact


def test_phone_redacted_including_hinglish_sentence():
    out, found = redact("mera number 9876543210 hai")
    assert "[PHONE]" in out
    assert "9876543210" not in out
    assert "PHONE" in found


def test_otp_contextual_redaction():
    out, found = redact("aapko OTP 445566 bheja hai")
    assert "[OTP]" in out
    assert "445566" not in out


def test_card_luhn_redacted_but_random_digits_kept():
    valid = "card 4242 4242 4242 4242 hai"  # passes Luhn
    out, found = redact(valid)
    assert "[CARD]" in out and "CARD" in found

    invalid = "reference 1234 5678 9012 3456"  # fails Luhn
    out2, found2 = redact(invalid)
    assert "[CARD]" not in out2


def test_email_and_aadhaar():
    out, found = redact("email priya@skillovilla.com aadhaar 1234 5678 9012")
    assert "[EMAIL]" in out and "[AADHAAR]" in out


def test_clean_text_untouched():
    text = "sir aap kaise hain, course accha hai"
    out, found = redact(text)
    assert out == text and found == []
