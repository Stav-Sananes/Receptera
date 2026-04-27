"""Summary schemas (Feature 3)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CallSummaryRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    transcript_lines: list[str] = Field(..., min_length=1, max_length=500)


class CallSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    topic: str = Field(..., max_length=200)
    key_points: list[str] = Field(default_factory=list, max_length=5)
    action_items: list[str] = Field(default_factory=list, max_length=10)
    raw_text: str
    model: str
    total_ms: int
