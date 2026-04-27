"""POST /api/summary — post-call Hebrew summary (Feature 3)."""

from __future__ import annotations

import json
import time

from fastapi import APIRouter, HTTPException

from receptra.llm.client import get_async_client, select_model
from receptra.llm.engine import _strip_markdown_fences
from receptra.summary.prompts import build_summary_messages
from receptra.summary.schema import CallSummary, CallSummaryRequest

router = APIRouter(prefix="/api/summary", tags=["summary"])


@router.post("", response_model=CallSummary)
async def generate_call_summary(body: CallSummaryRequest) -> CallSummary:
    """Generate a Hebrew structured summary of a completed call."""
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

    return CallSummary(
        topic=data.get("topic", ""),
        key_points=data.get("key_points", []),
        action_items=data.get("action_items", []),
        raw_text=raw,
        model=chosen_model,
        total_ms=total_ms,
    )
