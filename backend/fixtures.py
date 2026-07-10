"""Canned MOCK_MODE fixtures (rubric §4 config, §6.3 fixtures).

Shared by MockTranscriber and MockLLM so the transcript and the analysis stay
consistent: every evidence/flag `quote` is a verbatim substring of a segment,
so the quote-verification gate passes on real quotes. Selection is by
`raw_metadata["fixture"]` on the call; default is the "over_promiser" call,
which demonstrates the quote gate, PII redaction, AND the compliance cap
(dimension scores would compute to ~68 but a critical over-promise caps it at 40).

Segment tuple: (speaker, start_s, end_s, text).
"""

from __future__ import annotations

DEFAULT_FIXTURE = "over_promiser"

FIXTURES: dict[str, dict] = {
    "over_promiser": {
        "language": "hi",
        "segments": [
            ("advisor", 0.0, 5.0, "Hello sir, SkilloVilla se Arjun. Aap abhi kya kar rahe hain, aur data science mein aana chahte hain?"),
            ("customer", 5.0, 9.0, "Main abhi ek IT company mein support role mein hoon, growth nahi hai."),
            ("advisor", 9.0, 15.0, "Samajh gaya sir, aap career switch chahte hain. Aapka background dekhte hue humara program perfect rahega."),
            ("customer", 15.0, 18.0, "Par mujhe darr hai job milegi ya nahi."),
            ("advisor", 18.0, 24.0, "Sir tension mat lijiye, is course ke baad placement 100% guaranteed hai, job pakki samajhiye."),
            ("customer", 24.0, 27.0, "Achha, fees kitni hai?"),
            ("advisor", 27.0, 33.0, "Fees pachaas hazaar, EMI option bhi hai teen mahine ka, main aapko poora breakdown bhej deta hoon."),
            ("customer", 33.0, 36.0, "Theek hai, trial le sakta hoon?"),
            ("advisor", 36.0, 42.0, "Bilkul sir, main aaj shaam paanch baje ka trial slot book kar deta hoon, confirmation aa jayega."),
            ("advisor", 42.0, 48.0, "Payment ke liye aap apna card number aur OTP bata dijiye, main abhi enrollment process kar deta hoon."),
            ("customer", 48.0, 53.0, "Mera number 9876543210 hai, aur OTP 445566 abhi aaya hai."),
        ],
        "analysis": {
            "dimensions": [
                {"dimension": "needs_discovery", "score": 4, "evidence_quote": "Aap abhi kya kar rahe hain, aur data science mein aana chahte hain?"},
                {"dimension": "product_knowledge", "score": 4, "evidence_quote": "Fees pachaas hazaar, EMI option bhi hai teen mahine ka"},
                {"dimension": "objection_handling", "score": 3, "evidence_quote": "Aapka background dekhte hue humara program perfect rahega"},
                {"dimension": "compliance_integrity", "score": 1, "evidence_quote": "is course ke baad placement 100% guaranteed hai"},
                {"dimension": "next_step_booking", "score": 5, "evidence_quote": "trial slot book kar deta hoon"},
            ],
            "flags": [
                {"tag": "over_promising", "quote": "is course ke baad placement 100% guaranteed hai", "reason": "Advisor guaranteed 100% placement — a prohibited over-promise for edtech.", "confidence": 0.96},
                {"tag": "pii_exposure", "quote": "aap apna card number aur OTP bata dijiye", "reason": "Advisor solicited card number and OTP on the call.", "confidence": 0.9},
            ],
        },
    },
    "good_discovery": {
        "language": "hi",
        "segments": [
            ("advisor", 0.0, 5.0, "Hello ma'am, SkilloVilla se Priya. Aap currently kya kar rahi hain?"),
            ("customer", 5.0, 9.0, "Main final year student hoon, coding seekhna chahti hoon."),
            ("advisor", 9.0, 15.0, "Great, toh aap fresher hain. Aapko web development pasand hai ya data side?"),
            ("customer", 15.0, 18.0, "Data analytics mein interest hai."),
            ("advisor", 18.0, 25.0, "Perfect, humara data analytics track mein Python, SQL aur real projects hain, mentorship ke saath."),
            ("customer", 25.0, 28.0, "Fees aur time kitna lagega?"),
            ("advisor", 28.0, 35.0, "Fees chalis hazaar, ya teen mahine ki EMI. Course chaar mahine ka hai, koi hidden charge nahi."),
            ("customer", 35.0, 38.0, "Placement ka kya scene hai?"),
            ("advisor", 38.0, 45.0, "Hum placement support dete hain — resume, mock interviews, referrals. Guarantee nahi dete, par past results achhe rahe hain."),
            ("customer", 45.0, 48.0, "Theek hai, trial le sakti hoon?"),
            ("advisor", 48.0, 54.0, "Bilkul, kal subah gyaarah baje ka trial book kar deti hoon, confirmation bhej dungi."),
        ],
        "analysis": {
            "dimensions": [
                {"dimension": "needs_discovery", "score": 5, "evidence_quote": "Aapko web development pasand hai ya data side?"},
                {"dimension": "product_knowledge", "score": 5, "evidence_quote": "data analytics track mein Python, SQL aur real projects hain"},
                {"dimension": "objection_handling", "score": 4, "evidence_quote": "Hum placement support dete hain — resume, mock interviews, referrals"},
                {"dimension": "compliance_integrity", "score": 5, "evidence_quote": "Guarantee nahi dete, par past results achhe rahe hain"},
                {"dimension": "next_step_booking", "score": 5, "evidence_quote": "trial book kar deti hoon"},
            ],
            "flags": [],
        },
    },
    "pushy_pressure": {
        "language": "hi",
        "segments": [
            ("advisor", 0.0, 4.0, "Haan hello, SkilloVilla se Rohit. Aaj ek special offer chal raha hai."),
            ("customer", 4.0, 7.0, "Kya offer hai?"),
            ("advisor", 7.0, 12.0, "Course pachaas hazaar ka hai, par aaj enroll karo toh chalis hazaar mein."),
            ("customer", 12.0, 15.0, "Mujhe course ke baare mein kuch nahi pata abhi."),
            ("advisor", 15.0, 21.0, "Sir jaldi decide kijiye, offer aaj raat baarah baje khatam ho jayega, seats limited hain."),
            ("customer", 21.0, 24.0, "Main sochta hoon."),
            ("advisor", 24.0, 29.0, "Sochne ka time nahi hai sir, abhi payment kar do warna kal double price."),
            ("customer", 29.0, 31.0, "Theek hai baad mein."),
        ],
        "analysis": {
            "dimensions": [
                {"dimension": "needs_discovery", "score": 1, "evidence_quote": "Aaj ek special offer chal raha hai"},
                {"dimension": "product_knowledge", "score": 2, "evidence_quote": "Course pachaas hazaar ka hai"},
                {"dimension": "objection_handling", "score": 1, "evidence_quote": "Sochne ka time nahi hai sir"},
                {"dimension": "compliance_integrity", "score": 1, "evidence_quote": "offer aaj raat baarah baje khatam ho jayega"},
                {"dimension": "next_step_booking", "score": 1, "evidence_quote": "abhi payment kar do warna kal double price"},
            ],
            "flags": [
                {"tag": "price_before_value", "quote": "Course pachaas hazaar ka hai, par aaj enroll karo toh chalis hazaar mein", "reason": "Price quoted before any needs discovery or value framing.", "confidence": 0.82},
                {"tag": "pressure_tactics", "quote": "offer aaj raat baarah baje khatam ho jayega, seats limited hain", "reason": "False scarcity / artificial deadline to pressure the customer.", "confidence": 0.93},
                {"tag": "pressure_tactics", "quote": "abhi payment kar do warna kal double price", "reason": "Repeated hard close after a clear request for time.", "confidence": 0.9},
            ],
        },
    },
    "hidden_costs": {
        "language": "hi",
        "segments": [
            ("advisor", 0.0, 5.0, "Hello ma'am, SkilloVilla se Sneha. Aap data analytics seekhna chahti hain?"),
            ("customer", 5.0, 8.0, "Haan, fees kitni hai?"),
            ("advisor", 8.0, 13.0, "Bas chalis hazaar, aur kuch nahi, ekdum simple hai."),
            ("customer", 13.0, 16.0, "Koi aur charge toh nahi?"),
            ("advisor", 16.0, 22.0, "Registration ya EMI ke interest ki tension mat lijiye, woh sab main dekh lungi."),
            ("customer", 22.0, 25.0, "Theek hai, trial de sakti hoon?"),
            ("advisor", 25.0, 30.0, "Haan kal subah ka trial book kar deti hoon."),
        ],
        "analysis": {
            "dimensions": [
                {"dimension": "needs_discovery", "score": 3, "evidence_quote": "Aap data analytics seekhna chahti hain?"},
                {"dimension": "product_knowledge", "score": 3, "evidence_quote": "Bas chalis hazaar, aur kuch nahi"},
                {"dimension": "objection_handling", "score": 3, "evidence_quote": "woh sab main dekh lungi"},
                {"dimension": "compliance_integrity", "score": 1, "evidence_quote": "Registration ya EMI ke interest ki tension mat lijiye"},
                {"dimension": "next_step_booking", "score": 4, "evidence_quote": "kal subah ka trial book kar deti hoon"},
            ],
            "flags": [
                {"tag": "undisclosed_costs", "quote": "Registration ya EMI ke interest ki tension mat lijiye", "reason": "Registration fee and EMI interest waved away rather than disclosed.", "confidence": 0.86},
            ],
        },
    },
    "non_sales": {
        "language": "hi",
        "segments": [
            ("advisor", 0.0, 3.0, "Hello, kya main Rahul ji se baat kar raha hoon?"),
            ("customer", 3.0, 6.0, "Nahi, aapne galat number lagaya hai."),
            ("advisor", 6.0, 8.0, "Oh sorry, galti se lag gaya. Dhanyavaad."),
        ],
        "analysis": {"dimensions": [], "flags": [], "non_sales": True},
    },
}


def get_fixture(name: str | None) -> dict:
    return FIXTURES.get(name or DEFAULT_FIXTURE, FIXTURES[DEFAULT_FIXTURE])
