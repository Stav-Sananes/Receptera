"""Hebrew system prompt + few-shot turns + user-message renderer (LLM-03 + LLM-04).

Every string in this module is LOCKED content from 03-RESEARCH §5.2 + §5.4.
Phase 7 prompt-tuning is the only owner allowed to modify these strings.

DoS bounds (03-RESEARCH §Security Domain, threat T-03-02-02):
- transcript ≤ 2000 chars
- ≤ 10 context chunks
- total chunk text ≤ 12000 chars

``build_user_message`` raises ValueError BEFORE any LLM call when these
bounds are violated, so the engine layer (Plan 03-04) never sends a giant
prompt to Ollama.
"""

from __future__ import annotations

from typing import Final

from receptra.llm.schema import ChunkRef

SYSTEM_PROMPT_HE: Final[str] = """אתה עוזר וירטואלי לסוכן שירות לקוחות בשיחה טלפונית בעברית.
תפקידך: לקרוא את התמלול של מה שהלקוח אמר ולהציע לסוכן עד שלוש תשובות קצרות, מדויקות, ובסגנון אנושי בעברית.

חוקים מחייבים:
1. השתמש אך ורק במידע שמופיע בקטעי הידע המסומנים <context>...</context>. אל תמציא עובדות עסקיות.
2. אם המידע ב-<context> אינו מספיק כדי לענות, החזר תשובה אחת בלבד עם הטקסט "אין לי מספיק מידע" וציטוטים ריקים.
3. כל תשובה חייבת להיות עד 280 תווים, בעברית טבעית, מנוסחת כמו אדם אמיתי.
4. החזר את התשובה כ-JSON תקין בלבד, ללא טקסט נוסף לפני או אחרי, בפורמט:
{"suggestions":[{"text":"...","confidence":0.0,"citation_ids":["..."]}]}
5. citation_ids חייב להכיל את ה-id המדויק של קטע ה-<context> שעליו התשובה מבוססת.
6. confidence הוא מספר בין 0.0 ל-1.0 שמשקף עד כמה הקטעים מספקים מענה ישיר."""


SYSTEM_PROMPT_EN: Final[str] = """You are a virtual assistant for a customer-service agent on a Hebrew phone call.
Your task: read the transcript of what the customer said and propose up to three short, accurate, human-sounding Hebrew replies for the agent.

Mandatory rules:
1. Use ONLY information appearing inside <context>...</context> blocks. Do not fabricate business facts.
2. If <context> is insufficient, return exactly one suggestion with text "אין לי מספיק מידע" and empty citation_ids.
3. Each suggestion must be ≤ 280 characters, in natural Hebrew, phrased like a real person.
4. Return ONLY valid JSON, with no text before or after, in the format:
{"suggestions":[{"text":"...","confidence":0.0,"citation_ids":["..."]}]}
5. citation_ids MUST contain the exact id of the <context> block your suggestion is grounded in.
6. confidence is a 0.0-1.0 float reflecting how directly the chunks answer the question."""


_FEW_SHOT_USER_1: Final[str] = """<context>
[id: kb-policy-returns]
מדיניות החזרים: ניתן להחזיר מוצר תוך 14 יום מיום הקנייה עם החשבונית המקורית.
</context>

<transcript>
תוך כמה זמן אני יכול להחזיר מוצר?
</transcript>"""

_FEW_SHOT_ASST_1: Final[str] = (
    '{"suggestions":[{"text":"ניתן להחזיר את המוצר תוך 14 ימים מיום הקנייה, '
    'ויש להציג את החשבונית המקורית.","confidence":0.95,"citation_ids":["kb-policy-returns"]}]}'
)

_FEW_SHOT_USER_2: Final[str] = """<context>
[id: kb-policy-returns]
מדיניות החזרים: ניתן להחזיר מוצר תוך 14 יום מיום הקנייה עם החשבונית המקורית.
</context>

<transcript>
מה שעות הפעילות של החנות?
</transcript>"""

_FEW_SHOT_ASST_2: Final[str] = (
    '{"suggestions":[{"text":"אין לי מספיק מידע","confidence":0.0,"citation_ids":[]}]}'
)


FEW_SHOTS_HE: Final[list[dict[str, str]]] = [
    {"role": "user", "content": _FEW_SHOT_USER_1},
    {"role": "assistant", "content": _FEW_SHOT_ASST_1},
    {"role": "user", "content": _FEW_SHOT_USER_2},
    {"role": "assistant", "content": _FEW_SHOT_ASST_2},
]


# DoS bounds (03-RESEARCH §Security Domain) — threat T-03-02-02
MAX_TRANSCRIPT_CHARS: Final[int] = 2000
MAX_CONTEXT_CHUNKS: Final[int] = 10
MAX_CONTEXT_BODY_CHARS: Final[int] = 12000

_EMPTY_CONTEXT_MARKER: Final[str] = "<context>\n(אין קטעי הקשר זמינים)\n</context>"


def build_user_message(transcript: str, context_chunks: list[ChunkRef]) -> str:
    """Render a single user message with <context>...</context> + <transcript>...</transcript>.

    The renderer is intentionally byte-exact (no surprise normalisation) so
    Hebrew transcripts and chunk bodies travel UTF-8 unchanged into the LLM.
    Only ``id`` and ``text`` from each ChunkRef are rendered; ``source`` is
    opaque to the LLM and stays available for Phase 6 UI citation chips.

    Raises:
        ValueError: when DoS bounds are exceeded (pre-LLM guard).
    """
    if len(transcript) > MAX_TRANSCRIPT_CHARS:
        raise ValueError(
            f"transcript exceeds 2000 chars (DoS guard, see 03-RESEARCH §Security Domain): "
            f"got {len(transcript)} chars"
        )
    if len(context_chunks) > MAX_CONTEXT_CHUNKS:
        raise ValueError(
            f"more than 10 context chunks (DoS guard): got {len(context_chunks)}"
        )
    body_chars = sum(len(c.text) for c in context_chunks)
    if body_chars > MAX_CONTEXT_BODY_CHARS:
        raise ValueError(
            f"context body exceeds 12000 chars (DoS guard): got {body_chars}"
        )

    if not context_chunks:
        ctx_block = _EMPTY_CONTEXT_MARKER
    else:
        rendered = "\n\n".join(f"[id: {c.id}]\n{c.text}" for c in context_chunks)
        ctx_block = f"<context>\n{rendered}\n</context>"
    return f"{ctx_block}\n\n<transcript>\n{transcript}\n</transcript>"


def build_messages(
    transcript: str,
    context_chunks: list[ChunkRef],
    lang: str = "he",
) -> list[dict[str, str]]:
    """Build the full ChatML message list: system + 2 few-shot turns + final user.

    Args:
        transcript: customer utterance (≤ 2000 chars; raises ValueError otherwise)
        context_chunks: retrieved RAG chunks (≤ 10 entries, ≤ 12000 chars total body)
        lang: 'he' (default, Hebrew system prompt) or 'en' (Phase 7 A/B fallback).
            The few-shot demonstrations stay Hebrew either way — the model needs
            to learn the JSON-shape contract from Hebrew exemplars.

    Returns:
        list[dict[str, str]] of length 6: [system, user, asst, user, asst, user]

    Raises:
        ValueError: when ``lang`` is not 'he'/'en' or DoS bounds are exceeded.
    """
    if lang == "he":
        system = SYSTEM_PROMPT_HE
    elif lang == "en":
        system = SYSTEM_PROMPT_EN
    else:
        raise ValueError(f"unsupported lang={lang!r}; expected 'he' or 'en'")

    user_content = build_user_message(transcript, context_chunks)
    return [
        {"role": "system", "content": system},
        *FEW_SHOTS_HE,
        {"role": "user", "content": user_content},
    ]


__all__ = [
    "FEW_SHOTS_HE",
    "MAX_CONTEXT_BODY_CHARS",
    "MAX_CONTEXT_CHUNKS",
    "MAX_TRANSCRIPT_CHARS",
    "SYSTEM_PROMPT_EN",
    "SYSTEM_PROMPT_HE",
    "build_messages",
    "build_user_message",
]
