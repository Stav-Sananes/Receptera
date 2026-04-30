"""Summary schemas (Feature 3)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class FinalMeta(BaseModel):
    """Optional per-utterance metadata sent alongside transcript_lines so the
    CRM webhook (v1.2) can carry duration/latency without a second call."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    text: str
    duration_ms: int = 0
    stt_latency_ms: int = 0


class IntentMeta(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    label: str
    label_he: str


class CallSummaryRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    transcript_lines: list[str] = Field(..., min_length=1, max_length=500)
    # v1.2 webhook context — all optional, all backward-compatible.
    call_id: str | None = None
    finals_meta: list[FinalMeta] | None = None
    intent: IntentMeta | None = None


class CallSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    topic: str = Field(..., max_length=200)
    key_points: list[str] = Field(default_factory=list, max_length=5)
    action_items: list[str] = Field(default_factory=list, max_length=10)
    raw_text: str
    model: str
    total_ms: int
