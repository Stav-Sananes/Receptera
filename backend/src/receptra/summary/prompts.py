"""Hebrew system prompt + few-shot examples for post-call summary (Feature 3)."""

from __future__ import annotations

from typing import Final

MAX_SUMMARY_TRANSCRIPT_CHARS: Final[int] = 12_000

SYSTEM_PROMPT_SUMMARY_HE: Final[str] = """אתה עוזר המסכם שיחות טלפוניות עסקיות בעברית.
קיבלת תמלול של שיחה בין סוכן שירות לקוחות ללקוח.
תפקידך: לכתוב סיכום קצר ומובנה של השיחה.

כללים:
1. כתוב בעברית פשוטה וברורה.
2. כלול בדיוק את הסעיפים הבאים (אל תוסיף סעיפים אחרים):
   - topic: משפט אחד המתאר את הסיבה לפנייה.
   - key_points: עד 3 נקודות עיקריות שעלו בשיחה (רשימה).
   - action_items: מה הלקוח ביקש / מה הסוכן התחייב לעשות. אם אין — רשימה ריקה.
3. אל תמציא מידע שלא מופיע בתמלול.
4. החזר את הסיכום כ-JSON בלבד, ללא טקסט לפני או אחרי, בפורמט המדויק:
{"topic":"...","key_points":["..."],"action_items":["..."]}"""

_FEW_SHOT_USER: Final[str] = """<transcript>
לקוח: שלום, אני רוצה לבטל את ההזמנה שלי מאתמול, מספר הזמנה 12345.
סוכן: בוודאי, אני בודק. כן, ההזמנה ממתינה. האם יש סיבה לביטול?
לקוח: פשוט שיניתי את דעתי. מתי יוחזר התשלום?
סוכן: ההחזר יגיע תוך 3-5 ימי עסקים לכרטיס האשראי שלך.
</transcript>"""

_FEW_SHOT_ASST: Final[str] = (
    '{"topic":"ביטול הזמנה מס\' 12345",'
    '"key_points":["הלקוח ביקש ביטול הזמנה מהיום הקודם","הסוכן אישר את הביטול"],'
    '"action_items":["זיכוי כרטיס אשראי תוך 3-5 ימי עסקים"]}'
)


def build_summary_messages(transcript: str) -> list[dict[str, str]]:
    """Build the message list for the summary LLM call.

    Uses its OWN character budget (12000) — NEVER call build_messages() from
    llm/prompts.py here; that function has a 2000-char DoS guard for per-utterance
    transcripts and will raise ValueError on a full call transcript.
    """
    if len(transcript) > MAX_SUMMARY_TRANSCRIPT_CHARS:
        truncated = transcript[-MAX_SUMMARY_TRANSCRIPT_CHARS:]
    else:
        truncated = transcript
    return [
        {"role": "system", "content": SYSTEM_PROMPT_SUMMARY_HE},
        {"role": "user", "content": _FEW_SHOT_USER},
        {"role": "assistant", "content": _FEW_SHOT_ASST},
        {"role": "user", "content": f"<transcript>\n{truncated}\n</transcript>"},
    ]
