"""CallSense relational schema (rubric §5).

Design notes worth defending:
- Closed taxonomies (job/flag/dimension states) are Python enums rendered as
  VARCHAR + CHECK (native_enum=False): app-side type safety and DB-side
  integrity, without the pain of ALTER TYPE when a taxonomy grows.
- `raw_metadata JSONB` on calls preserves the untouched vendor payload so a
  mapping bug can be re-mapped later without re-fetching — source-agnostic
  without schema churn.
- `idempotency_key` UNIQUE on calls dissolves duplicate deliveries at the DB.
- `rubric_version` + `prompt_hash` stamp every score so scores are only ever
  compared within a version, and prompt drift is detectable.
- `call_scores` is a materialised composite (one row per call) so dashboards
  don't recompute the weighted sum on every read; rollups above it are SQL
  views (see views.sql).
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base, TimestampMixin


# --------------------------------------------------------------------------
# Closed taxonomies
# --------------------------------------------------------------------------
class CallStatus(str, enum.Enum):
    received = "received"
    processing = "processing"
    done = "done"
    failed = "failed"
    needs_review = "needs_review"


class JobStage(str, enum.Enum):
    transcribe = "transcribe"
    diarise = "diarise"
    redact = "redact"
    classify = "classify"
    analyse = "analyse"
    validate = "validate"


class JobStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"
    dead = "dead"


class SpeakerRole(str, enum.Enum):
    advisor = "advisor"
    customer = "customer"
    unknown = "unknown"


class RubricDimension(str, enum.Enum):
    needs_discovery = "needs_discovery"
    product_knowledge = "product_knowledge"
    objection_handling = "objection_handling"
    compliance_integrity = "compliance_integrity"
    next_step_booking = "next_step_booking"


class FlagTag(str, enum.Enum):
    no_needs_discovery = "no_needs_discovery"
    over_promising = "over_promising"
    pressure_tactics = "pressure_tactics"
    price_before_value = "price_before_value"
    undisclosed_costs = "undisclosed_costs"
    weak_trial_booking = "weak_trial_booking"
    talk_over_customer = "talk_over_customer"
    pii_exposure = "pii_exposure"
    non_sales_call = "non_sales_call"


class FlagSeverity(str, enum.Enum):
    info = "info"
    warn = "warn"
    critical = "critical"


class FlagState(str, enum.Enum):
    open = "open"
    disputed = "disputed"
    upheld = "upheld"
    dismissed = "dismissed"


class CalibrationVerdict(str, enum.Enum):
    true_positive = "true_positive"
    false_positive = "false_positive"


def _enum(py_enum: type[enum.Enum], length: int = 32):
    """VARCHAR + CHECK rendering of a Python enum (portable, easy to evolve)."""
    return Enum(py_enum, native_enum=False, length=length, validate_strings=True)


# --------------------------------------------------------------------------
# Org hierarchy
# --------------------------------------------------------------------------
class Org(Base, TimestampMixin):
    __tablename__ = "orgs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    teams: Mapped[list["Team"]] = relationship(back_populates="org")


class Team(Base, TimestampMixin):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(
        ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # A TL is themselves an advisor row; nullable + use_alter breaks the
    # teams<->advisors circular FK for migration ordering.
    team_leader_id: Mapped[int | None] = mapped_column(
        ForeignKey("advisors.id", use_alter=True, name="fk_teams_team_leader"),
        nullable=True,
    )

    org: Mapped[Org] = relationship(back_populates="teams")
    advisors: Mapped[list["Advisor"]] = relationship(
        back_populates="team", foreign_keys="Advisor.team_id"
    )


class Advisor(Base, TimestampMixin):
    __tablename__ = "advisors"

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    # Array of external CRM/dialer agent-IDs that map to this advisor. Resolution
    # is `external_ids ? :agent_ref`. A new dialer's IDs UPSERT in with no code
    # change; org growth without reconfig.
    external_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )

    team: Mapped[Team] = relationship(
        back_populates="advisors", foreign_keys=[team_id]
    )
    calls: Mapped[list["Call"]] = relationship(back_populates="advisor")


# --------------------------------------------------------------------------
# Calls + pipeline
# --------------------------------------------------------------------------
class Call(Base, TimestampMixin):
    __tablename__ = "calls"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_calls_idempotency_key"),
        Index("ix_calls_advisor_id", "advisor_id"),
        Index("ix_calls_org_id", "org_id"),
        Index("ix_calls_called_at", "called_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(
        ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False
    )
    advisor_id: Mapped[int | None] = mapped_column(
        ForeignKey("advisors.id", ondelete="SET NULL"), nullable=True
    )
    customer_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False)  # folder|rest|crm
    source_call_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # sha256(audio_bytes)+source_id — UNIQUE, the double-delivery guard.
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    audio_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    called_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    channels: Mapped[int | None] = mapped_column(Integer, nullable=True)
    language_hint: Mapped[str | None] = mapped_column(String(20), nullable=True)
    raw_metadata: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    status: Mapped[CallStatus] = mapped_column(
        _enum(CallStatus), nullable=False, default=CallStatus.received
    )

    advisor: Mapped[Advisor | None] = relationship(back_populates="calls")
    jobs: Mapped[list["ProcessingJob"]] = relationship(back_populates="call")
    transcript: Mapped["Transcript | None"] = relationship(back_populates="call")
    scores: Mapped[list["Score"]] = relationship(back_populates="call")
    flags: Mapped[list["Flag"]] = relationship(back_populates="call")
    call_score: Mapped["CallScore | None"] = relationship(back_populates="call")


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"
    __table_args__ = (
        # The queue claim query filters on (status, run_after); index it.
        Index("ix_jobs_claim", "status", "run_after"),
        Index("ix_jobs_call_id", "call_id"),
        UniqueConstraint("call_id", "stage", name="uq_jobs_call_stage"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    call_id: Mapped[int] = mapped_column(
        ForeignKey("calls.id", ondelete="CASCADE"), nullable=False
    )
    stage: Mapped[JobStage] = mapped_column(_enum(JobStage), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        _enum(JobStatus), nullable=False, default=JobStatus.pending
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    run_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    call: Mapped[Call] = relationship(back_populates="jobs")


# --------------------------------------------------------------------------
# Transcription + diarisation
# --------------------------------------------------------------------------
class Transcript(Base, TimestampMixin):
    __tablename__ = "transcripts"

    id: Mapped[int] = mapped_column(primary_key=True)
    call_id: Mapped[int] = mapped_column(
        ForeignKey("calls.id", ondelete="CASCADE"), nullable=False, index=True
    )
    engine: Mapped[str] = mapped_column(String(50), nullable=False)
    language: Mapped[str | None] = mapped_column(String(20), nullable=True)
    code_switch_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    wer_estimate: Mapped[float | None] = mapped_column(Float, nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")

    call: Mapped[Call] = relationship(back_populates="transcript")
    segments: Mapped[list["Segment"]] = relationship(
        back_populates="transcript", order_by="Segment.idx"
    )


class Segment(Base):
    __tablename__ = "segments"
    __table_args__ = (
        Index("ix_segments_transcript_id", "transcript_id"),
        CheckConstraint("end_s >= start_s", name="ck_segments_time_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    transcript_id: Mapped[int] = mapped_column(
        ForeignKey("transcripts.id", ondelete="CASCADE"), nullable=False
    )
    idx: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker: Mapped[SpeakerRole] = mapped_column(
        _enum(SpeakerRole), nullable=False, default=SpeakerRole.unknown
    )
    start_s: Mapped[float] = mapped_column(Float, nullable=False)
    end_s: Mapped[float] = mapped_column(Float, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # PII-masked text used for everything downstream (LLM never sees raw).
    redacted_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    transcript: Mapped[Transcript] = relationship(back_populates="segments")


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------
class Score(Base):
    __tablename__ = "scores"
    __table_args__ = (
        Index("ix_scores_call_id", "call_id"),
        CheckConstraint("raw_score >= 0 AND raw_score <= 5", name="ck_scores_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    call_id: Mapped[int] = mapped_column(
        ForeignKey("calls.id", ondelete="CASCADE"), nullable=False
    )
    rubric_version: Mapped[str] = mapped_column(String(20), nullable=False)
    dimension: Mapped[RubricDimension] = mapped_column(
        _enum(RubricDimension), nullable=False
    )
    raw_score: Mapped[int] = mapped_column(Integer, nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_start_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    prompt_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    call: Mapped[Call] = relationship(back_populates="scores")


class CallScore(Base):
    """Materialised per-call composite (0-100). One row per call."""

    __tablename__ = "call_scores"

    call_id: Mapped[int] = mapped_column(
        ForeignKey("calls.id", ondelete="CASCADE"), primary_key=True
    )
    composite: Mapped[float] = mapped_column(Float, nullable=False)
    rubric_version: Mapped[str] = mapped_column(String(20), nullable=False)
    compliance_capped: Mapped[bool] = mapped_column(
        nullable=False, server_default="false"
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    call: Mapped[Call] = relationship(back_populates="call_score")


# --------------------------------------------------------------------------
# Flags + dispute loop
# --------------------------------------------------------------------------
class Flag(Base):
    __tablename__ = "flags"
    __table_args__ = (
        Index("ix_flags_call_id", "call_id"),
        Index("ix_flags_state", "state"),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_flags_confidence"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    call_id: Mapped[int] = mapped_column(
        ForeignKey("calls.id", ondelete="CASCADE"), nullable=False
    )
    tag: Mapped[FlagTag] = mapped_column(_enum(FlagTag), nullable=False)
    severity: Mapped[FlagSeverity] = mapped_column(_enum(FlagSeverity), nullable=False)
    start_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    end_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    state: Mapped[FlagState] = mapped_column(
        _enum(FlagState), nullable=False, default=FlagState.open
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    call: Mapped[Call] = relationship(back_populates="flags")
    disputes: Mapped[list["Dispute"]] = relationship(back_populates="flag")


class Dispute(Base):
    __tablename__ = "disputes"
    __table_args__ = (Index("ix_disputes_flag_id", "flag_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    flag_id: Mapped[int] = mapped_column(
        ForeignKey("flags.id", ondelete="CASCADE"), nullable=False
    )
    raised_by: Mapped[int | None] = mapped_column(
        ForeignKey("advisors.id", ondelete="SET NULL"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    resolution: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # upheld | dismissed
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    flag: Mapped[Flag] = relationship(back_populates="disputes")


class CalibrationExample(Base, TimestampMixin):
    """Resolved disputes become few-shot examples that tighten precision."""

    __tablename__ = "calibration_examples"

    id: Mapped[int] = mapped_column(primary_key=True)
    tag: Mapped[FlagTag] = mapped_column(_enum(FlagTag), nullable=False, index=True)
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    verdict: Mapped[CalibrationVerdict] = mapped_column(
        _enum(CalibrationVerdict), nullable=False
    )
    source_dispute_id: Mapped[int | None] = mapped_column(
        ForeignKey("disputes.id", ondelete="SET NULL"), nullable=True
    )


# --------------------------------------------------------------------------
# Audit
# --------------------------------------------------------------------------
class AuditLog(Base):
    """Append-only record of every human action. Never UPDATE/DELETE."""

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_entity", "entity", "entity_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    actor: Mapped[str] = mapped_column(String(120), nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    before: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
