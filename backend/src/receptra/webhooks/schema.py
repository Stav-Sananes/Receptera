"""Webhook payload schema — versioned envelope for downstream consumers.

`schema_version` is bumped on any breaking change. Receivers should
ignore unknown fields (forward-compat) and reject unknown versions.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class WebhookSummary(BaseModel):
    """Trimmed CallSummary — same shape as receptra.summary.schema.CallSummary
    minus the fat raw_text field. Receivers usually don't need raw."""

    model_config = ConfigDict(extra="forbid")

    topic: str
    key_points: list[str] = Field(default_factory=list)
    action_items: list[str] = Field(default_factory=list)
    model: str
    total_ms: int


class WebhookIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    label_he: str


class WebhookFinal(BaseModel):
    """One utterance line in the call transcript."""

    model_config = ConfigDict(extra="forbid")

    text: str
    duration_ms: int
    stt_latency_ms: int


class WebhookPayload(BaseModel):
    """Envelope POSTed to ``settings.webhook_url`` after every summary."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = "1"
    event: Literal["call.summary"] = "call.summary"
    call_id: str
    ts_utc: str
    summary: WebhookSummary
    intent: WebhookIntent | None = None
    finals: list[WebhookFinal] = Field(default_factory=list)


__all__ = ["WebhookFinal", "WebhookIntent", "WebhookPayload", "WebhookSummary"]
