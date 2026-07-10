"""Prompt construction for analysis + classification (rubric §2.5, §6.1).

The rubric is inlined with concrete 0/5 anchors, the tag taxonomy is closed, the
evidence rule ("quote verbatim in the original language, omit if unsure") drives
precision, and resolved-dispute calibration few-shots are injected per run.
"""

from __future__ import annotations

from analysis.schema import AnalysisResult

SYSTEM = (
    "You are a meticulous sales-QA analyst for SkilloVilla, an Indian edtech that "
    "sells career-upskilling programs via tele-advisors. Calls are Hinglish "
    "(Hindi-English code-switched). You judge advisor behaviour against a fixed "
    "rubric and flag mis-selling. You are precise, not punitive: when a violation "
    "is ambiguous, you omit it. You return ONLY JSON matching the given schema."
)

_ANCHORS = [
    ("needs_discovery", "0 = no questions about goals/background; "
     "5 = open questions AND the pitch references the customer's answers."),
    ("product_knowledge", "0 = vague/incorrect program details; "
     "5 = accurate curriculum, mentorship, placement-support specifics."),
    ("objection_handling", "0 = ignores/bulldozes concerns; "
     "5 = acknowledges, clarifies, resolves with evidence, checks satisfaction."),
    ("compliance_integrity", "0 = guarantees, hidden costs, pressure; "
     "5 = honest expectations, full cost disclosure incl. EMI/loan terms."),
    ("next_step_booking", "0 = nothing scheduled; 5 = a concrete trial slot booked."),
]

_TAGS = [
    "no_needs_discovery (warn), over_promising (critical), pressure_tactics (critical),",
    "price_before_value (warn), undisclosed_costs (critical), weak_trial_booking (warn),",
    "talk_over_customer (info), pii_exposure (warn), non_sales_call (info).",
]


def build_analysis_user_prompt(
    transcript: str, calibration: list[dict] | None = None
) -> str:
    anchors = "\n".join(f"- {name}: {desc}" for name, desc in _ANCHORS)
    tags = " ".join(_TAGS)
    parts = [
        "Score this call on each dimension (integer 0-5) with a verbatim evidence "
        "quote, and list any issue flags.",
        "",
        "RUBRIC DIMENSIONS (weights are fixed elsewhere):",
        anchors,
        "",
        "ISSUE TAGS (use ONLY these; omit a flag if you are not confident):",
        tags,
        "",
        "RULES:",
        "- Every dimension score and every flag MUST include a `quote` that appears "
        "VERBATIM in the transcript, in the original language. Do not paraphrase or "
        "translate quotes.",
        "- Emit a per-flag `confidence` 0-1 (0.9+ = explicit verbatim violation; "
        "0.6 = implied). Do NOT invent timestamps.",
        "- Return ONLY JSON of the form: "
        '{"dimensions":[{"dimension","score","evidence_quote"}],'
        '"flags":[{"tag","quote","reason","confidence"}]}',
    ]
    if calibration:
        parts += ["", "CALIBRATION EXAMPLES (learn from past human decisions):"]
        for ex in calibration:
            verdict = "IS" if ex["verdict"] == "true_positive" else "is NOT"
            parts.append(f'- "{ex["quote"]}" {verdict} a valid {ex["tag"]}.')
    parts += ["", "TRANSCRIPT:", transcript]
    return "\n".join(parts)


def build_classify_prompt(opening_text: str) -> str:
    return (
        "Is the following the opening of a genuine SALES conversation, or a "
        "NON-SALES call (wrong number, internal, spam)? Answer with exactly one "
        f"word: SALES or NON_SALES.\n\n{opening_text}"
    )


# Expose the schema for callers/tests that want to show it.
ANALYSIS_JSON_SCHEMA = AnalysisResult.model_json_schema()
