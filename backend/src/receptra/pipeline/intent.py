"""Intent detection for live utterances (v1.1 F4).

``detect_intent(transcript)`` classifies a single utterance into one of six
Hebrew call-centre categories using DictaLM with ``num_predict=10`` (one word).

``detect_intent_and_send(transcript, ws, utterance_id)`` wraps the above and
fires one ``IntentDetected`` WS event.  All exceptions are swallowed — intent
failure must never crash the suggest pipeline.

Intended call site (``stt/pipeline.py``)::

    results = await asyncio.gather(
        suggest(text, t_speech_end_ms, utterance_id),
        detect_intent_and_send(text, ws, utterance_id),
        return_exceptions=True,
    )
    for r in results:
        if isinstance(r, BaseException):
            logger.bind(event="pipeline.intent_error").warning({"err": str(r)})
"""

from __future__ import annotations

import contextlib
from typing import Final

from loguru import logger

from receptra.llm.client import get_async_client, select_model
from receptra.pipeline.events import IntentDetected

# ── Hebrew label → English canonical key ──────────────────────────────────────

INTENT_LABELS: Final[dict[str, str]] = {
    "הזמנה": "booking",
    "תלונה": "complaint",
    "חיוב": "billing",
    "מידע": "information",
    "ביטול": "cancellation",
    "אחר": "other",
}

# Reverse: English → Hebrew display string
_LABEL_HE: Final[dict[str, str]] = {v: k for k, v in INTENT_LABELS.items()}

# ── Prompt ────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT_INTENT_HE: Final[str] = (
    "אתה מסווג כוונות לקוחות בשיחות טלפון בעברית.\n"
    "קיבלת משפט של לקוח. עליך לזהות את כוונת הלקוח מתוך הקטגוריות הבאות בלבד:\n"
    "הזמנה, תלונה, חיוב, מידע, ביטול, אחר.\n\n"
    "חוקים:\n"
    "1. החזר מילה אחת בלבד — שם הקטגוריה בעברית.\n"
    "2. אל תוסיף שום הסבר, סימני פיסוק, או טקסט נוסף.\n"
    "3. אם אינך בטוח — החזר \"אחר\"."
)

_FEW_SHOT_1_USER: Final[str] = "אני רוצה לקבוע תור לשיניים ביום שלישי"
_FEW_SHOT_1_ASST: Final[str] = "הזמנה"

_FEW_SHOT_2_USER: Final[str] = "החשבון שקיבלתי לא נכון, חויבתי פעמיים"
_FEW_SHOT_2_ASST: Final[str] = "חיוב"

_FEW_SHOT_3_USER: Final[str] = "מה שעות הפתיחה שלכם?"
_FEW_SHOT_3_ASST: Final[str] = "מידע"

_MAX_TRANSCRIPT_CHARS: Final[int] = 500  # DoS guard — intent needs only first ~100


def _build_intent_messages(transcript: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT_INTENT_HE},
        {"role": "user", "content": _FEW_SHOT_1_USER},
        {"role": "assistant", "content": _FEW_SHOT_1_ASST},
        {"role": "user", "content": _FEW_SHOT_2_USER},
        {"role": "assistant", "content": _FEW_SHOT_2_ASST},
        {"role": "user", "content": _FEW_SHOT_3_USER},
        {"role": "assistant", "content": _FEW_SHOT_3_ASST},
        {"role": "user", "content": transcript[:_MAX_TRANSCRIPT_CHARS]},
    ]


# ── Public API ─────────────────────────────────────────────────────────────────


async def detect_intent(transcript: str) -> str:
    """Classify transcript into one canonical English intent label.

    Returns one of: ``booking``, ``complaint``, ``billing``, ``information``,
    ``cancellation``, ``other``.  Never raises — unknown model output → ``other``.
    """
    client = get_async_client()
    chosen_model = await select_model(client)
    response = await client.chat(
        model=chosen_model,
        messages=_build_intent_messages(transcript),
        stream=False,
        options={"temperature": 0.0, "num_predict": 10},
    )
    raw = (response.message.content or "אחר").strip().rstrip(".")
    return INTENT_LABELS.get(raw, "other")


async def detect_intent_and_send(
    transcript: str,
    ws: object,  # FastAPI WebSocket; typed as object to avoid heavy import
    utterance_id: str,
) -> None:
    """Classify intent and fire one ``intent_detected`` event on the WebSocket.

    All exceptions are swallowed — intent failure must not crash the pipeline.
    """
    with contextlib.suppress(Exception):
        try:
            label = await detect_intent(transcript)
        except Exception as exc:
            logger.bind(event="pipeline.intent_error").warning(
                {"utterance_id": utterance_id, "err": str(exc)}
            )
            return

        label_he = _LABEL_HE.get(label, "אחר")
        event = IntentDetected(
            label=label,  # type: ignore[arg-type]
            label_he=label_he,
            utterance_id=utterance_id,
        )
        await ws.send_json(event.model_dump())  # type: ignore[attr-defined]


__all__ = ["INTENT_LABELS", "detect_intent", "detect_intent_and_send"]
