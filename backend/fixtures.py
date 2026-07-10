"""Canned MOCK_MODE fixtures (rubric §4 config, §6.3 fixtures).

Domain: FitNova — a Bangalore fitness & wellness coaching platform (the case
study's company). Calls are Hinglish tele-sales for personal-training / coaching
programs and free trial sessions.

Shared by MockTranscriber and MockLLM so the transcript and analysis stay
consistent: every evidence/flag `quote` is a verbatim substring of a segment, so
the quote-verification gate passes on real quotes. Default is the "over_promiser"
call, which demonstrates the quote gate, PII redaction, AND the compliance cap
(dimension scores would compute to ~68 but a critical "weight loss guaranteed"
over-promise caps it at 40).

Segment tuple: (speaker, start_s, end_s, text).
"""

from __future__ import annotations

DEFAULT_FIXTURE = "over_promiser"

FIXTURES: dict[str, dict] = {
    "over_promiser": {
        "language": "hi",
        "segments": [
            ("advisor", 0.0, 5.0, "Hello sir, FitNova se Arjun. Aap apni fitness journey ke liye kya goal rakhte hain?"),
            ("customer", 5.0, 9.0, "Mujhe weight kam karna hai, office ki wajah se time nahi milta."),
            ("advisor", 9.0, 15.0, "Samajh gaya sir, busy schedule hai. Humara online personal training aapke liye perfect rahega."),
            ("customer", 15.0, 18.0, "Par results aayenge ya nahi, thoda doubt hai."),
            ("advisor", 18.0, 24.0, "Sir tension mat lijiye, teen mahine mein weight loss 100% guaranteed hai, pakka result milega."),
            ("customer", 24.0, 27.0, "Achha, fees kitni hai?"),
            ("advisor", 27.0, 33.0, "Fees pandrah hazaar teen mahine ka, EMI option bhi hai, main aapko poora plan bhej deta hoon."),
            ("customer", 33.0, 36.0, "Theek hai, trial session le sakta hoon?"),
            ("advisor", 36.0, 42.0, "Bilkul sir, main aaj shaam ka free trial session book kar deta hoon, coach aapko call karega."),
            ("advisor", 42.0, 48.0, "Payment ke liye aap apna card number aur OTP bata dijiye, main abhi enrollment kar deta hoon."),
            ("customer", 48.0, 53.0, "Mera number 9876543210 hai, aur OTP 445566 abhi aaya hai."),
        ],
        "analysis": {
            "dimensions": [
                {"dimension": "needs_discovery", "score": 4, "evidence_quote": "Aap apni fitness journey ke liye kya goal rakhte hain?"},
                {"dimension": "product_knowledge", "score": 4, "evidence_quote": "Fees pandrah hazaar teen mahine ka, EMI option bhi hai"},
                {"dimension": "objection_handling", "score": 3, "evidence_quote": "Humara online personal training aapke liye perfect rahega"},
                {"dimension": "compliance_integrity", "score": 1, "evidence_quote": "teen mahine mein weight loss 100% guaranteed hai"},
                {"dimension": "next_step_booking", "score": 5, "evidence_quote": "free trial session book kar deta hoon"},
            ],
            "flags": [
                {"tag": "over_promising", "quote": "teen mahine mein weight loss 100% guaranteed hai", "reason": "Advisor guaranteed 100% weight-loss results in 3 months — a prohibited over-promise for a coaching program.", "confidence": 0.96},
                {"tag": "pii_exposure", "quote": "aap apna card number aur OTP bata dijiye", "reason": "Advisor solicited card number and OTP on the call.", "confidence": 0.9},
            ],
        },
    },
    "good_discovery": {
        "language": "hi",
        "segments": [
            ("advisor", 0.0, 5.0, "Hello ma'am, FitNova se Priya. Aap currently kaise fit rehti hain, koi routine hai?"),
            ("customer", 5.0, 9.0, "Bas kabhi kabhi walk karti hoon, proper routine nahi hai."),
            ("advisor", 9.0, 15.0, "Samajh gayi. Aapka main goal weight loss hai, stamina, ya general fitness?"),
            ("customer", 15.0, 18.0, "General fitness aur thoda stamina."),
            ("advisor", 18.0, 25.0, "Perfect, humare program mein personal coach, weekly diet plan aur live sessions milte hain."),
            ("customer", 25.0, 28.0, "Fees aur duration kitna hai?"),
            ("advisor", 28.0, 35.0, "Fees barah hazaar, ya teen mahine ki EMI. Program chaar mahine ka hai, koi hidden charge nahi."),
            ("customer", 35.0, 38.0, "Results ki guarantee hai?"),
            ("advisor", 38.0, 45.0, "Ma'am hum effort aur consistency pe results dete hain, guarantee nahi dete, par members ke achhe results rahe hain."),
            ("customer", 45.0, 48.0, "Theek hai, trial le sakti hoon?"),
            ("advisor", 48.0, 54.0, "Bilkul, kal subah ka free trial session book kar deti hoon, confirmation bhej dungi."),
        ],
        "analysis": {
            "dimensions": [
                {"dimension": "needs_discovery", "score": 5, "evidence_quote": "Aapka main goal weight loss hai, stamina, ya general fitness?"},
                {"dimension": "product_knowledge", "score": 5, "evidence_quote": "personal coach, weekly diet plan aur live sessions milte hain"},
                {"dimension": "objection_handling", "score": 4, "evidence_quote": "hum effort aur consistency pe results dete hain"},
                {"dimension": "compliance_integrity", "score": 5, "evidence_quote": "guarantee nahi dete, par members ke achhe results rahe hain"},
                {"dimension": "next_step_booking", "score": 5, "evidence_quote": "free trial session book kar deti hoon"},
            ],
            "flags": [],
        },
    },
    "pushy_pressure": {
        "language": "hi",
        "segments": [
            ("advisor", 0.0, 4.0, "Haan hello, FitNova se Rohit. Aaj ek special fitness offer chal raha hai."),
            ("customer", 4.0, 7.0, "Kya offer hai?"),
            ("advisor", 7.0, 12.0, "Program pandrah hazaar ka hai, par aaj join karo toh dus hazaar mein."),
            ("customer", 12.0, 15.0, "Mujhe program ke baare mein kuch pata nahi abhi."),
            ("advisor", 15.0, 21.0, "Sir jaldi decide kijiye, offer aaj raat khatam ho jayega, sirf paanch slots bache hain."),
            ("customer", 21.0, 24.0, "Main sochta hoon."),
            ("advisor", 24.0, 29.0, "Sochne ka time nahi hai sir, abhi payment kar do warna kal se purana price."),
            ("customer", 29.0, 31.0, "Theek hai baad mein."),
        ],
        "analysis": {
            "dimensions": [
                {"dimension": "needs_discovery", "score": 1, "evidence_quote": "Aaj ek special fitness offer chal raha hai"},
                {"dimension": "product_knowledge", "score": 2, "evidence_quote": "Program pandrah hazaar ka hai"},
                {"dimension": "objection_handling", "score": 1, "evidence_quote": "Sochne ka time nahi hai sir"},
                {"dimension": "compliance_integrity", "score": 1, "evidence_quote": "offer aaj raat khatam ho jayega"},
                {"dimension": "next_step_booking", "score": 1, "evidence_quote": "abhi payment kar do warna kal se purana price"},
            ],
            "flags": [
                {"tag": "price_before_value", "quote": "Program pandrah hazaar ka hai, par aaj join karo toh dus hazaar mein", "reason": "Price quoted before any needs discovery or value framing.", "confidence": 0.82},
                {"tag": "pressure_tactics", "quote": "offer aaj raat khatam ho jayega, sirf paanch slots bache hain", "reason": "False scarcity / artificial deadline to pressure the customer.", "confidence": 0.93},
                {"tag": "pressure_tactics", "quote": "abhi payment kar do warna kal se purana price", "reason": "Repeated hard close after a clear request for time.", "confidence": 0.9},
            ],
        },
    },
    "hidden_costs": {
        "language": "hi",
        "segments": [
            ("advisor", 0.0, 5.0, "Hello ma'am, FitNova se Sneha. Aap fitness program join karna chahti hain?"),
            ("customer", 5.0, 8.0, "Haan, fees kitni hai?"),
            ("advisor", 8.0, 13.0, "Bas barah hazaar, aur kuch nahi, ekdum simple hai."),
            ("customer", 13.0, 16.0, "Koi aur charge toh nahi?"),
            ("advisor", 16.0, 22.0, "Registration fee aur auto-renewal ke baare mein abhi mat sochiye, woh sab main dekh lungi."),
            ("customer", 22.0, 25.0, "Theek hai, trial de sakti hoon?"),
            ("advisor", 25.0, 30.0, "Haan kal subah ka trial book kar deti hoon."),
        ],
        "analysis": {
            "dimensions": [
                {"dimension": "needs_discovery", "score": 3, "evidence_quote": "Aap fitness program join karna chahti hain?"},
                {"dimension": "product_knowledge", "score": 3, "evidence_quote": "Bas barah hazaar, aur kuch nahi"},
                {"dimension": "objection_handling", "score": 3, "evidence_quote": "woh sab main dekh lungi"},
                {"dimension": "compliance_integrity", "score": 1, "evidence_quote": "Registration fee aur auto-renewal ke baare mein abhi mat sochiye"},
                {"dimension": "next_step_booking", "score": 4, "evidence_quote": "kal subah ka trial book kar deti hoon"},
            ],
            "flags": [
                {"tag": "undisclosed_costs", "quote": "Registration fee aur auto-renewal ke baare mein abhi mat sochiye", "reason": "Registration fee and auto-renewal waved away rather than disclosed.", "confidence": 0.86},
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
