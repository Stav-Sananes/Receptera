"""POST /api/summary — post-call Hebrew summary (Feature 3)."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from loguru import logger

from receptra.config import settings
from receptra.llm.client import get_async_client, select_model
from receptra.llm.engine import _strip_markdown_fences
from receptra.summary.prompts import build_summary_messages
from receptra.summary.schema import CallSummary, CallSummaryRequest
from receptra.webhooks.schema import (
    WebhookFinal,
    WebhookIntent,
    WebhookPayload,
    WebhookSummary,
)
from receptra.webhooks.sender import send_webhook

router = APIRouter(prefix="/api/summary", tags=["summary"])

# Outstanding fire-and-forget webhook tasks. Module-level set holds strong
# refs so asyncio doesn't GC them mid-flight. Each task self-removes on done.
_webhook_tasks: set[asyncio.Task[None]] = set()


@router.post("", response_model=CallSummary)
async def generate_call_summary(body: CallSummaryRequest) -> CallSummary:
    """Generate a Hebrew structured summary of a completed call.

    On success, asynchronously fires a CRM webhook (v1.2) if
    ``settings.webhook_url`` is configured. Webhook is fire-and-forget —
    delivery failures do NOT affect the HTTP response to the agent's UI.
    """
    transcript = "\n".join(body.transcript_lines)
    messages = build_summary_messages(transcript)

    client = get_async_client()
    chosen_model = await select_model(client)
    t0 = time.perf_counter()
    try:
        response = await client.chat(
            model=chosen_model,
            messages=messages,
            stream=False,
            options={"temperature": 0.0, "num_predict": 1024, "num_ctx": 8192},
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"LLM unavailable: {exc}") from exc
    total_ms = int((time.perf_counter() - t0) * 1000)

    raw = (response.message.content or "").strip()
    cleaned = _strip_markdown_fences(raw)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail=f"LLM returned invalid JSON: {exc}") from exc

    summary = CallSummary(
        topic=data.get("topic", ""),
        key_points=data.get("key_points", []),
        action_items=data.get("action_items", []),
        raw_text=raw,
        model=chosen_model,
        total_ms=total_ms,
    )

    # Fire-and-forget webhook. If webhook_url is empty, send_webhook
    # short-circuits to False — no outbound traffic, no extra latency.
    # Holding a reference (RUF006) so the task isn't garbage-collected mid-flight.
    if settings.webhook_url:
        _webhook_tasks.add(
            t := asyncio.create_task(_fire_webhook(summary, body))
        )
        t.add_done_callback(_webhook_tasks.discard)

    return summary


async def _fire_webhook(summary: CallSummary, request: CallSummaryRequest) -> None:
    """Build the webhook envelope and dispatch. Failures are swallowed —
    the agent's UI already got the summary; webhook is best-effort."""
    try:
        finals: list[WebhookFinal]
        if request.finals_meta:
            finals = [
                WebhookFinal(
                    text=f.text,
                    duration_ms=f.duration_ms,
                    stt_latency_ms=f.stt_latency_ms,
                )
                for f in request.finals_meta
            ]
        else:
            # Fallback when frontend sent only transcript_lines
            finals = [WebhookFinal(text=line, duration_ms=0, stt_latency_ms=0)
                      for line in request.transcript_lines]

        intent_meta = (
            WebhookIntent(label=request.intent.label, label_he=request.intent.label_he)
            if request.intent
            else None
        )

        payload = WebhookPayload(
            call_id=request.call_id or "call-" + datetime.now(UTC).strftime("%Y%m%d%H%M%S"),
            ts_utc=datetime.now(UTC).isoformat(),
            summary=WebhookSummary(
                topic=summary.topic,
                key_points=list(summary.key_points),
                action_items=list(summary.action_items),
                model=summary.model,
                total_ms=summary.total_ms,
            ),
            intent=intent_meta,
            finals=finals,
        )
        await send_webhook(payload)
    except Exception as exc:
        logger.bind(event="webhook.dispatch_error").error({"err": str(exc)})
