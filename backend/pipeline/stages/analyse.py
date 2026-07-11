"""Stage 5: ANALYSE — LLM rubric + tags, then the anti-hallucination gate.

Flow (rubric §6.3):
1. LLM returns forced JSON; Pydantic validates (one retry on failure).
2. Every dimension/flag quote is verified against the transcript; unmatched
   flags are DROPPED (quote-or-it-didn't-happen).
3. Timestamps are derived from the matched segment (code, not the model).
4. Low-confidence flags degrade to `info`; critical tags drive the compliance cap.
5. Scores + flags + the materialised composite are written; every score is
   stamped with rubric_version + prompt_hash.
"""

from __future__ import annotations

import hashlib
import logging

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from analysis.llm import get_llm
from analysis.metrics import TALK_RATIO_THRESHOLD, talk_ratio
from analysis.prompts import SYSTEM, build_analysis_user_prompt
from analysis.rubric import (
    CONFIDENCE_THRESHOLD,
    DIMENSION_WEIGHTS,
    RUBRIC_VERSION,
    TAG_SEVERITY,
    compute_composite,
)
from analysis.schema import AnalysisResult
from analysis.verify import verify_quote
from app.config import get_settings
from db.models import FlagSeverity, FlagState
from pipeline.stages.base import load_call, load_tx_segments

log = logging.getLogger("callsense.stage.analyse")


def run(session: Session, call_id: int) -> None:
    if session.execute(
        text("SELECT 1 FROM call_scores WHERE call_id = :id"), {"id": call_id}
    ).first():
        log.info("call %s already scored; skipping", call_id)
        return

    settings = get_settings()
    call = load_call(session, call_id)
    segments = load_tx_segments(session, call_id, redacted=True)
    transcript = "\n".join(f"{s.speaker}: {s.text}" for s in segments)
    calibration = _load_calibration(session)

    llm = get_llm(call.fixture)
    result = _analyse_with_retry(llm, transcript, calibration)

    prompt_hash = hashlib.sha256(
        (SYSTEM + build_analysis_user_prompt(transcript, calibration)).encode()
    ).hexdigest()
    if settings.mock_mode:
        model_name = "mock"
    elif settings.llm_provider == "anthropic" and settings.anthropic_api_key:
        model_name = settings.llm_model
    else:
        model_name = settings.gemini_model

    # --- Dimension scores -------------------------------------------------
    dim_scores: dict = {}
    for dim in result.dimensions:
        match = verify_quote(dim.evidence_quote, segments)
        dim_scores[dim.dimension] = dim.score
        session.execute(
            text(
                """
                INSERT INTO scores
                    (call_id, rubric_version, dimension, raw_score, weight,
                     evidence_quote, evidence_start_s, model, prompt_hash, created_at)
                VALUES (:cid, :rv, :dim, :score, :w, :q, :st, :model, :ph, now())
                """
            ),
            {
                "cid": call_id, "rv": RUBRIC_VERSION, "dim": dim.dimension.value,
                "score": dim.score, "w": DIMENSION_WEIGHTS.get(dim.dimension, 0.0),
                "q": dim.evidence_quote,
                "st": match.start_s if match.found else None,
                "model": model_name, "ph": prompt_hash,
            },
        )

    # --- Flags (quote-gated) ---------------------------------------------
    has_critical = False
    kept, dropped = 0, 0
    for flag in result.flags:
        match = verify_quote(flag.quote, segments)
        if not match.found:
            dropped += 1
            log.warning(
                "dropped hallucinated flag %s for call %s (best ratio %.2f): %r",
                flag.tag.value, call_id, match.ratio, flag.quote,
            )
            continue

        severity = TAG_SEVERITY.get(flag.tag, FlagSeverity.info)
        # Precision-over-recall: low confidence degrades to info-for-review.
        if flag.confidence < CONFIDENCE_THRESHOLD:
            severity = FlagSeverity.info
        if severity is FlagSeverity.critical:
            has_critical = True

        session.execute(
            text(
                """
                INSERT INTO flags
                    (call_id, tag, severity, start_s, end_s, quote, reason,
                     confidence, state, created_at)
                VALUES (:cid, :tag, :sev, :st, :en, :q, :reason, :conf, :state, now())
                """
            ),
            {
                "cid": call_id, "tag": flag.tag.value, "sev": severity.value,
                "st": match.start_s, "en": match.end_s, "q": flag.quote,
                "reason": flag.reason, "conf": flag.confidence,
                "state": FlagState.open.value,
            },
        )
        kept += 1

    # --- Deterministic metric flag: talk ratio ----------------------------
    # Computed by code from diarised segment durations, never by the LLM.
    ratio = talk_ratio(segments)
    if ratio is not None:
        session.execute(
            text(
                "UPDATE calls SET raw_metadata = raw_metadata || "
                "CAST(:patch AS jsonb) WHERE id = :cid"
            ),
            {"patch": f'{{"talk_ratio": {ratio}}}', "cid": call_id},
        )
        if ratio > TALK_RATIO_THRESHOLD:
            session.execute(
                text(
                    """
                    INSERT INTO flags
                        (call_id, tag, severity, quote, reason, confidence,
                         state, created_at)
                    VALUES (:cid, 'talk_over_customer', 'info', NULL, :reason,
                            1.0, 'open', now())
                    """
                ),
                {
                    "cid": call_id,
                    "reason": (
                        f"Advisor spoke {ratio:.0%} of the conversation "
                        f"(threshold {TALK_RATIO_THRESHOLD:.0%}) — measured from "
                        "diarised segment durations."
                    ),
                },
            )
            kept += 1

    # --- Composite (with compliance cap) ---------------------------------
    composite, capped = compute_composite(dim_scores, has_critical)
    session.execute(
        text(
            """
            INSERT INTO call_scores
                (call_id, composite, rubric_version, compliance_capped, computed_at)
            VALUES (:cid, :comp, :rv, :capped, now())
            """
        ),
        {"cid": call_id, "comp": composite, "rv": RUBRIC_VERSION, "capped": capped},
    )
    log.info(
        "call %s analysed: composite=%.1f%s, flags kept=%d dropped=%d",
        call_id, composite, " (capped)" if capped else "", kept, dropped,
    )


def _analyse_with_retry(llm, transcript: str, calibration: list[dict]) -> AnalysisResult:
    raw = llm.analyse(transcript, calibration)
    try:
        return AnalysisResult.model_validate_json(raw)
    except ValidationError as first:
        log.warning("analysis schema invalid, retrying once: %s", first)
        raw = llm.analyse(transcript, calibration)
        return AnalysisResult.model_validate_json(raw)  # raises -> stage fails cleanly


def _load_calibration(session: Session, limit: int = 5) -> list[dict]:
    rows = session.execute(
        text(
            "SELECT tag, quote, verdict FROM calibration_examples "
            "ORDER BY id DESC LIMIT :n"
        ),
        {"n": limit},
    ).mappings().all()
    return [dict(r) for r in rows]
