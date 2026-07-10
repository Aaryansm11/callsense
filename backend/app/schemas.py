"""Request/response models for the API (Pydantic — same validation story as the
LLM output). Read endpoints mostly return plain dicts from SQL; these cover
request bodies and the couple of responses worth typing."""

from __future__ import annotations

from pydantic import BaseModel, Field


class IngestResponse(BaseModel):
    accepted: bool
    created: bool
    call_id: int | None = None
    reason: str | None = None
    processed_inline: bool = False


class DisputeCreate(BaseModel):
    note: str | None = None
    raised_by: int | None = None  # advisor id (role switcher stub)


class DisputeResolve(BaseModel):
    resolution: str = Field(description="'upheld' or 'dismissed'")
    resolved_by: str | None = None
    resolution_note: str | None = None
