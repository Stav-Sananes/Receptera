"""HTTP routes for /api/webhooks/* — config status + test trigger.

Two endpoints:

- GET  /api/webhooks/status  — operator-facing config status (URL set?
  signed? — never returns the secret itself).
- POST /api/webhooks/test    — fire a hardcoded synthetic payload to
  verify the receiver works end-to-end.

The "real" webhook firing happens inline from receptra.summary.router.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter

from receptra.config import settings
from receptra.webhooks.schema import (
    WebhookFinal,
    WebhookIntent,
    WebhookPayload,
    WebhookSummary,
)
from receptra.webhooks.sender import send_webhook

router = APIRouter()


@router.get("/status")
async def webhook_status() -> dict[str, bool | str]:
    """Operator-safe config view (does not return the secret)."""
    return {
        "configured": bool(settings.webhook_url),
        "signed": bool(settings.webhook_secret),
        "url_host": _safe_host(settings.webhook_url),
    }


def _safe_host(url: str) -> str:
    """Return host portion only — useful for UI without exposing a full URL with tokens."""
    if not url:
        return ""
    try:
        from urllib.parse import urlparse

        return urlparse(url).hostname or ""
    except Exception:
        return ""


@router.post("/test")
async def webhook_test() -> dict[str, bool | str]:
    """Fire a synthetic payload at the configured webhook_url."""
    if not settings.webhook_url:
        return {"ok": False, "reason": "webhook_url not configured"}

    payload = WebhookPayload(
        call_id="test-" + datetime.now(UTC).strftime("%Y%m%d%H%M%S"),
        ts_utc=datetime.now(UTC).isoformat(),
        summary=WebhookSummary(
            topic="בדיקת חיבור webhook",
            key_points=["payload סינתטי", "אין PII אמיתי"],
            action_items=["ודא שה-receiver מחזיר 2xx"],
            model="dictalm3",
            total_ms=0,
        ),
        intent=WebhookIntent(label="other", label_he="אחר"),
        finals=[
            WebhookFinal(text="זוהי בדיקת webhook", duration_ms=1500, stt_latency_ms=100)
        ],
    )

    delivered = await send_webhook(payload)
    return {"ok": delivered, "reason": "" if delivered else "delivery failed — see backend logs"}


__all__ = ["router"]
