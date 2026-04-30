"""Async webhook sender with HMAC-SHA256 signature + exponential backoff retry.

Single public coroutine: ``send_webhook(payload)``. Reads URL/secret/timeout
from settings each call so a hot config reload (future feature) is supported
without process restart.

Retry policy:
    attempt 1 → fail → sleep 1s
    attempt 2 → fail → sleep 2s
    attempt 3 → fail → give up, log "webhook.failed"

5xx and connection errors retry. 4xx (auth, validation) do NOT retry —
the request is malformed and re-sending will not help.

PII boundary: log lines emit method+url_hash+status+duration only. Never
the body, never the secret, never decoded transcript text.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json

import httpx
from loguru import logger

from receptra.config import settings
from receptra.webhooks.schema import WebhookPayload

_MAX_ATTEMPTS = 3
_BACKOFFS_S = [1.0, 2.0, 4.0]  # one extra in case the loop is bumped to 4


def _sign(body: bytes, secret: str) -> str:
    """Hex HMAC-SHA256 — same shape as GitHub/Stripe webhooks."""
    mac = hmac.new(secret.encode("utf-8"), body, hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


def _url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]


async def send_webhook(payload: WebhookPayload) -> bool:
    """POST the payload to ``settings.webhook_url``.

    Returns True on 2xx within the retry budget, False otherwise. Never raises.
    Returns False immediately when ``webhook_url`` is empty (off by default).
    """
    url = settings.webhook_url.strip()
    if not url:
        return False

    body = payload.model_dump_json().encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Receptra-Webhook/1.0",
        "X-Receptra-Event": payload.event,
        "X-Receptra-Schema": payload.schema_version,
        "X-Receptra-Call-Id": payload.call_id,
    }
    if settings.webhook_secret:
        headers["X-Receptra-Signature"] = _sign(body, settings.webhook_secret)

    url_h = _url_hash(url)

    async with httpx.AsyncClient(timeout=settings.webhook_timeout_s) as client:
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            t0 = asyncio.get_event_loop().time()
            try:
                resp = await client.post(url, content=body, headers=headers)
                duration_ms = int((asyncio.get_event_loop().time() - t0) * 1000)
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                logger.bind(event="webhook.network_error").warning(
                    {
                        "attempt": attempt,
                        "url_hash": url_h,
                        "err": type(exc).__name__,
                    }
                )
                if attempt < _MAX_ATTEMPTS:
                    await asyncio.sleep(_BACKOFFS_S[attempt - 1])
                    continue
                return False

            if 200 <= resp.status_code < 300:
                logger.bind(event="webhook.delivered").info(
                    {
                        "attempt": attempt,
                        "url_hash": url_h,
                        "status": resp.status_code,
                        "duration_ms": duration_ms,
                        "call_id": payload.call_id,
                    }
                )
                return True

            # 4xx — do not retry. Operator misconfigured the receiver.
            if 400 <= resp.status_code < 500:
                logger.bind(event="webhook.client_error").error(
                    {
                        "attempt": attempt,
                        "url_hash": url_h,
                        "status": resp.status_code,
                        "duration_ms": duration_ms,
                    }
                )
                return False

            # 5xx — retry.
            logger.bind(event="webhook.server_error").warning(
                {
                    "attempt": attempt,
                    "url_hash": url_h,
                    "status": resp.status_code,
                    "duration_ms": duration_ms,
                }
            )
            if attempt < _MAX_ATTEMPTS:
                await asyncio.sleep(_BACKOFFS_S[attempt - 1])

    logger.bind(event="webhook.failed").error(
        {"url_hash": url_h, "call_id": payload.call_id, "attempts": _MAX_ATTEMPTS}
    )
    return False


def verify_signature(body: bytes, header_value: str, secret: str) -> bool:
    """Helper for receivers — constant-time HMAC verify.

    Exposed so any Python receiver can `from receptra.webhooks.sender import verify_signature`
    without copy-pasting the algorithm.
    """
    expected = _sign(body, secret)
    return hmac.compare_digest(expected, header_value)


__all__ = ["send_webhook", "verify_signature"]


# Avoid an unused-import warning in static analysis.
_ = json  # type: ignore[unused-ignore]
