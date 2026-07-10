"""Pydantic models for the LLM's structured output (rubric §2.6, §6.3.1).

The `dimension` and `tag` fields are enums (closed taxonomy) — the model
literally cannot invent a tag. Pydantic re-validates every field on receipt;
an invalid response triggers one retry-with-error, then dead-letters. Same
validation mechanism as the API's front door — one validation story.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from db.models import FlagTag, RubricDimension


class DimensionScore(BaseModel):
    dimension: RubricDimension
    score: int = Field(ge=0, le=5)
    evidence_quote: str


class RawFlag(BaseModel):
    tag: FlagTag
    quote: str
    reason: str
    confidence: float = Field(ge=0.0, le=1.0)


class AnalysisResult(BaseModel):
    dimensions: list[DimensionScore] = Field(default_factory=list)
    flags: list[RawFlag] = Field(default_factory=list)

    @classmethod
    def model_json_schema_str(cls) -> str:
        return json.dumps(cls.model_json_schema(), indent=2)
