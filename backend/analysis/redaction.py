"""PII redaction (rubric §2.14, §6.4) — runs BEFORE any text reaches the LLM.

Two layers, though only the regex layer is enabled by default (spaCy NER for
names/addresses is available but gated behind an optional import to avoid a model
download). Order matters: card (Luhn-checked) before Aadhaar before phone so the
longer patterns win. The raw text stays in a restricted column; `redacted_text`
is what everything downstream sees.
"""

from __future__ import annotations

import re

EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
CARD = re.compile(r"\b(?:\d[ -]?){13,16}\b")
AADHAAR = re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b")
OTP_CTX = re.compile(r"\b(otp|code|password)\b[^\d]{0,8}(\d{4,8})", re.IGNORECASE)
PHONE = re.compile(r"(?:\+91[\s-]?)?\b[6-9]\d{9}\b")
PAN = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")


def _luhn_ok(digits: str) -> bool:
    nums = [int(c) for c in digits if c.isdigit()]
    if len(nums) < 13:
        return False
    total, parity = 0, len(nums) % 2
    for i, n in enumerate(nums):
        if i % 2 == parity:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def redact(text: str) -> tuple[str, list[str]]:
    """Return (redacted_text, list_of_pii_types_found)."""
    found: list[str] = []

    def mark(kind: str) -> str:
        found.append(kind)
        return f"[{kind}]"

    text = EMAIL.sub(lambda m: mark("EMAIL"), text)

    def card_sub(m: re.Match) -> str:
        return mark("CARD") if _luhn_ok(m.group(0)) else m.group(0)

    text = CARD.sub(card_sub, text)
    text = AADHAAR.sub(lambda m: mark("AADHAAR"), text)
    text = OTP_CTX.sub(lambda m: f"{m.group(1)} " + mark("OTP"), text)
    text = PHONE.sub(lambda m: mark("PHONE"), text)
    text = PAN.sub(lambda m: mark("PAN"), text)

    # De-dup while preserving order.
    return text, list(dict.fromkeys(found))
