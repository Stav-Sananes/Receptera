#!/usr/bin/env python3
"""Wave-0 spike: validate the Hebrew char→BGE-M3 token ratio (Plan 04-01).

The Plan 04-02 chunker uses a 1-token≈3-Hebrew-char heuristic to size chunks
to ~500 BGE-M3 tokens (RESEARCH §Hebrew Chunking Strategy). If that heuristic
is off by >20%, chunks either bust the embedder context or under-pack the
window; this spike validates the heuristic against the actual BGE-M3
tokenizer on 5 representative Hebrew samples.

Modes:
- LIVE: ``transformers`` + ``sentencepiece`` installed AND ``BAAI/bge-m3``
  cached. Tokenizes each sample, computes per-sample chars/token ratio,
  emits MEASURED report.
- AIRGAP: import or cache miss. Writes UNMEASURED placeholder, exit 0.
  (Plan 02-01 precedent: spike never blocks downstream work.)

This script is intentionally NOT importable from the receptra package — it
is a standalone CLI for the Wave-0 contributor and is invoked by the verify
block. ``transformers``/``sentencepiece`` are NOT in pyproject.toml: silent
runtime dep additions are forbidden per Plan 02-05 lock.

Usage:
    python scripts/spike_chunk_token_ratio.py
    python scripts/spike_chunk_token_ratio.py --json
    python scripts/spike_chunk_token_ratio.py --out path/to/RESULTS.md
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# --- Module-level constants (auditable without re-running) ---

HEURISTIC_CHARS_PER_TOKEN = 3.0
DEVIATION_TOLERANCE_PCT = 20.0
MODEL_ID = "BAAI/bge-m3"

# 5 hand-crafted Hebrew samples. Topics mirror eventual Plan 04-06 KB fixture
# topics so spike inputs are domain-representative. Lengths span the chunker's
# operating range: ~500 / ~1000 / ~1500 / ~2000 / ~3000 chars.

SAMPLE_HOURS_500 = (
    # Topic: store opening hours.
    "החנות פתוחה בימים ראשון עד חמישי בין השעות תשע בבוקר לשבע בערב. "
    "ביום שישי החנות פתוחה משעה תשע בבוקר עד שעה אחת בצהריים בלבד. "
    "במוצאי שבת החנות נפתחת רק שעה לאחר צאת השבת ועד השעה אחת עשרה בלילה. "
    "בחגים החנות סגורה ביום החג עצמו ובערב החג היא סוגרת מוקדם יותר. "
    "בחול המועד החנות פתוחה בשעות פעילות חלקיות. "
    "מומלץ להתקשר לפני ההגעה כדי לוודא שעות פתיחה עדכניות בחגים. "
    "בקיץ אנחנו מאריכים שעות בשעה אחת. "
)

SAMPLE_RETURNS_1000 = (
    # Topic: returns / refunds policy.
    "מדיניות החזרת מוצרים שלנו מאפשרת ללקוח להחזיר כל מוצר בתוך ארבעה עשר יום מתאריך הקנייה. "
    "המוצר חייב להיות ארוז באריזה המקורית עם כל התוויות הנלוות. "
    "החזרת המוצר תתבצע מול קבלה תקפה או חשבונית מס. "
    "מוצרים שנפתחו ושימושם הותחל לא ניתנים להחזרה למעט במקרה של פגם ייצור מובהק. "
    "במקרה של פגם ייצור הלקוח זכאי להחלפה מלאה או החזר כספי לבחירתו. "
    "ההחזר הכספי מבוצע בתוך שבעה ימי עסקים מרגע אישור הבקשה. "
    "במקרה של תשלום באשראי ההחזר מבוצע לכרטיס המקורי בלבד. "
    "במקרה של מתנה ניתן לקבל זיכוי בלבד ולא החזר כספי. "
    "מוצרי מבצע אינם ניתנים להחזרה אלא להחלפה. "
    "אנחנו ממליצים לשמור על הקבלה במשך כל תקופת האחריות. "
    "במקרה של בעיה ניתן לפנות לשירות הלקוחות בטלפון או באימייל. "
    "צוות שירות הלקוחות שלנו זמין בשעות הפעילות הרגילות של החנות. "
)

SAMPLE_PRICES_1500 = (
    # Topic: pricing tiers.
    "מחירון השירותים שלנו בנוי בשלושה מסלולים עיקריים המותאמים לצרכים שונים של עסקים קטנים ובינוניים. "
    "המסלול הבסיסי כולל את כל הפיצ'רים החיוניים להפעלת הצ'אט בוט באתר וברשתות החברתיות. "
    "המסלול המתקדם מוסיף יכולות אינטגרציה מול מערכות CRM ניהול לקוחות מובילות בישראל ובעולם. "
    "המסלול המקצועי כולל גם פיצ'רים של הוצאת תובנות אנליטיות ודוחות מותאמים לפי דרישת הלקוח. "
    "בכל מסלול אנחנו מעניקים תמיכה טכנית של מומחה ייעודי בעברית בשעות הפעילות. "
    "תמיכה חירום בשעות הלילה ובסופי שבוע ניתנת רק במסלול המקצועי. "
    "המחיר במסלול הבסיסי הוא מאתיים תשעים ותשע שקלים לחודש כולל מע''מ. "
    "המחיר במסלול המתקדם הוא חמש מאות תשעים ותשע שקלים לחודש כולל מע''מ. "
    "המחיר במסלול המקצועי הוא תשע מאות תשעים ותשע שקלים לחודש כולל מע''מ. "
    "בהתחייבות לשנתיים מקבלים הנחה של חמישה עשר אחוז על כל אחד מהמסלולים. "
    "אנחנו מציעים תקופת ניסיון של ארבעה עשר יום ללא חיוב בכל אחד מהמסלולים. "
    "המעבר בין המסלולים אפשרי בכל עת ללא קנס ביטול. "
    "השדרוג מהמסלול הבסיסי לאחד המסלולים הגבוהים מתבצע מיידית. "
    "השנמוך לעולם לא מבוצע באמצע מחזור חיוב אלא בתחילת המחזור הבא. "
    "בכל מסלול ניתן לבקש פגישת התנעה ראשונית עם מומחה הטמעה. "
    "פגישת ההתנעה כלולה במחיר במסלול המתקדם והמקצועי בלבד. "
    "במסלול הבסיסי פגישת ההתנעה ניתנת בתשלום נוסף. "
    "אנחנו מאמינים בשקיפות מלאה ולכן אין הפתעות ולא דמי ביטול נסתרים. "
)

SAMPLE_ADDRESS_2000 = (
    # Topic: physical address + directions + parking.
    "המשרד שלנו ממוקם ברחוב הברזל מספר שלושים ושמונה בקומה החמישית בתל אביב צפון. "
    "הכניסה למבנה היא דרך הלובי הראשי וניתן לעלות במעלית או במדרגות. "
    "המעלית פועלת בכל שעות היממה אך הלובי סגור בלילה ובסופי שבוע. "
    "כניסה מחוץ לשעות הפעילות דורשת תיאום מראש מול קב''ט המבנה. "
    "החנייה למבקרים נמצאת בקומת הקרקע מתחת למבנה ויש בה שלושים מקומות. "
    "החנייה ללא תשלום בשעות הפעילות אך מוגבלת לשעתיים לכל מבקר. "
    "ניתן להאריך את זמן החנייה בתאום מראש עם המזכירות. "
    "תחבורה ציבורית כוללת קווי אוטובוס שלוש ארבע ושבע עשרה היורדים בתחנה הקרובה. "
    "הרכבת הקרובה היא תחנת תל אביב אוניברסיטה במרחק עשר דקות הליכה. "
    "מתחנת הרכבת ניתן ללכת ברגל או להזמין מונית או להשתמש בקורקינט שיתופי. "
    "ליד המבנה יש תחנת קורקינטים שיתופיים של חברת ליים. "
    "אנחנו ממליצים להגיע ברכבת בשעות הבוקר העמוסות כדי לחסוך זמן בפקקים. "
    "אם אתם מגיעים ברכב פרטי כדאי לבדוק את מצב הכבישים מראש. "
    "האזור עמוס במיוחד בין השעות שבע וחצי לתשע בבוקר. "
    "בחזרה אחר הצהריים האזור עמוס בין ארבע וחצי לשש וחצי. "
    "במקרה של פקק קיצוני ניתן לתאם פגישה מקוונת באמצעות זום או גוגל מיט. "
    "אנחנו מצוידים גם בחדר ישיבות עם ציוד היברידי המאפשר השתתפות מקוונת ופיזית. "
    "חדר הישיבות הראשי מתאים לשמונה משתתפים סביב השולחן ועוד חמישה במצב ועידה. "
    "חדר הישיבות הקטן מתאים עד ארבעה משתתפים ומיועד לפגישות אישיות. "
    "ניתן לבקש קפה ושתייה קרה ללא תשלום בכל פגישה במשרד. "
    "במידה ויש צורך בהזמנת ארוחה אנחנו עובדים עם מספר מסעדות באזור. "
    "תפריטי המסעדות זמינים אצל המזכירות לפי בקשה. "
    "אנחנו מבקשים להגיע בזמן לכל פגישה כדי לכבד את שאר המוזמנים. "
    "במקרה של איחור צפוי מעבר לחמש דקות נשמח לעדכון מראש. "
    "תודה על שיתוף הפעולה ונשמח לראותכם במשרד. "
)

SAMPLE_COMPLAINTS_3000 = (
    # Topic: complaints handling procedure.
    "תהליך הטיפול בתלונות לקוחות שלנו פתוח שקוף ומובנה. "
    "כל פנייה של לקוח נרשמת במערכת ייעודית ומקבלת מספר מעקב ייחודי. "
    "מספר המעקב נשלח ללקוח באימייל ובהודעת טקסט תוך עשר דקות מהפנייה. "
    "הלקוח יכול לראות את סטטוס הטיפול בכל עת באמצעות הקישור באימייל. "
    "השלב הראשון הוא קבלת הפנייה ובחינה ראשונית של נציג שירות לקוחות. "
    "השלב השני הוא הקלדת הפנייה לאחד משלושה מסלולים לפי חומרת הבעיה. "
    "מסלול ירוק לבעיות כלליות ושאלות פשוטות עם זמן מענה של עד שני ימי עסקים. "
    "מסלול צהוב לבעיות בינוניות הדורשות ברור מעמיק עם זמן מענה של עד חמישה ימי עסקים. "
    "מסלול אדום לבעיות חמורות או דחופות עם זמן מענה של עד עשרים וארבע שעות. "
    "השלב השלישי הוא חקירה מעמיקה של הצוות הרלוונטי ויצירת קשר עם הלקוח לקבלת פרטים נוספים. "
    "השלב הרביעי הוא הצעת פתרון ללקוח באמצעות הערוץ המועדף עליו. "
    "השלב החמישי הוא מימוש הפתרון לאחר אישור הלקוח. "
    "השלב השישי הוא סגירת הפנייה ושליחת סקר שביעות רצון ללקוח. "
    "במידה והלקוח אינו מרוצה מהפתרון יש לו זכות לערער בתוך שבעה ימים. "
    "הערעור נבחן על ידי מנהל מחלקת שירות הלקוחות ולא על ידי הנציג שטיפל בתחילה. "
    "במקרה של ערעור זמן המענה הוא עד עשרה ימי עסקים. "
    "אם הלקוח עדיין אינו מרוצה לאחר הערעור הוא יכול לפנות ליועצת המשפטית של החברה. "
    "היועצת המשפטית מטפלת בפניות מורכבות במיוחד או בכאלה הכוללות היבטים משפטיים. "
    "אנחנו מתחייבים לשקיפות מלאה לאורך כל התהליך. "
    "כל החלטה מנומקת בכתב והלקוח מקבל העתק שלה. "
    "המסמכים נשמרים במערכת לתקופה של שבע שנים לפי דרישות החוק. "
    "הלקוח יכול לבקש בכל עת עותק של כל המסמכים הקשורים לפנייתו. "
    "במקרה של תלונה הקשורה לעובד ספציפי הטיפול בתלונה יבוצע על ידי גורם נטרלי שאינו ממונה ישיר של אותו עובד. "
    "אנחנו מקפידים על חיסיון וצנעת הפרט של הלקוח לאורך כל התהליך. "
    "פרטי התלונה לא יחשפו בפני גורמים שאינם נדרשים לטיפול בה. "
    "במקרה של תלונה על עובד העובד יקבל הזדמנות הוגנת להגיב לטענות. "
    "במקרה של תלונה מוצדקת ננקטים הצעדים הנדרשים לתיקון הבעיה ולמניעת הישנותה. "
    "אנחנו לומדים מכל תלונה ומשתמשים בלקחים לשיפור השירות והתהליכים. "
    "מערכת הניהול שלנו מאפשרת זיהוי מגמות וחזרות של בעיות דומות. "
    "כאשר אנחנו מזהים מגמה כזו אנחנו פותחים פרויקט ייעודי לטיפול שורש. "
    "פרויקטים אלה מתועדים ותוצאותיהם מוצגות בדוח השנתי של החברה. "
    "אנחנו מאמינים שתלונות הן הזדמנות אמיתית לשפר את השירות שלנו. "
    "תודה לכל לקוח שטורח ומדווח על בעיות אנחנו מעריכים את הפנייה. "
)

SAMPLE_TEXTS: list[tuple[str, str]] = [
    ("hours_500", SAMPLE_HOURS_500),
    ("returns_1000", SAMPLE_RETURNS_1000),
    ("prices_1500", SAMPLE_PRICES_1500),
    ("address_2000", SAMPLE_ADDRESS_2000),
    ("complaints_3000", SAMPLE_COMPLAINTS_3000),
]


@dataclass(frozen=True)
class SampleMeasurement:
    name: str
    chars: int
    tokens: int
    chars_per_token: float


def _try_load_tokenizer() -> Any | None:
    """Return a transformers AutoTokenizer for BGE-M3, or None if unavailable.

    Wraps the expensive import + the HF cache lookup in a single try/except
    boundary. If transformers is not installed OR sentencepiece is missing
    OR the model is not cached and offline, returns None — caller switches
    to airgap mode. No network calls in default path.
    """
    try:
        from transformers import AutoTokenizer  # type: ignore[import-not-found]
    except ImportError:
        return None
    try:
        return AutoTokenizer.from_pretrained(MODEL_ID)
    except Exception:
        # Anything from HuggingFace cache miss / offline mode / sentencepiece
        # missing — fall back to airgap.
        return None


def _measure_live(tok: Any) -> list[SampleMeasurement]:
    out: list[SampleMeasurement] = []
    for name, text in SAMPLE_TEXTS:
        encoded = tok.encode(text)
        n_tokens = len(encoded)
        n_chars = len(text)
        ratio = n_chars / n_tokens if n_tokens > 0 else 0.0
        out.append(
            SampleMeasurement(
                name=name, chars=n_chars, tokens=n_tokens, chars_per_token=ratio
            )
        )
    return out


def _build_summary(measurements: list[SampleMeasurement]) -> dict[str, Any]:
    ratios = [m.chars_per_token for m in measurements]
    mean = sum(ratios) / len(ratios)
    deviation_pct = abs(mean - HEURISTIC_CHARS_PER_TOKEN) / HEURISTIC_CHARS_PER_TOKEN * 100.0
    return {
        "status": "MEASURED",
        "model_id": MODEL_ID,
        "sample_count": len(measurements),
        "heuristic_chars_per_token": HEURISTIC_CHARS_PER_TOKEN,
        "mean_chars_per_token": round(mean, 3),
        "min_chars_per_token": round(min(ratios), 3),
        "max_chars_per_token": round(max(ratios), 3),
        "deviation_pct": round(deviation_pct, 2),
        "deviation_tolerance_pct": DEVIATION_TOLERANCE_PCT,
        "heuristic_within_tolerance": deviation_pct <= DEVIATION_TOLERANCE_PCT,
        "measurements": [
            {
                "sample": m.name,
                "chars": m.chars,
                "tokens": m.tokens,
                "chars_per_token": round(m.chars_per_token, 3),
            }
            for m in measurements
        ],
    }


def _build_airgap_summary() -> dict[str, Any]:
    return {
        "status": "UNMEASURED",
        "model_id": MODEL_ID,
        "sample_count": len(SAMPLE_TEXTS),
        "heuristic_chars_per_token": HEURISTIC_CHARS_PER_TOKEN,
        "mean_chars_per_token": HEURISTIC_CHARS_PER_TOKEN,
        "deviation_pct": None,
        "deviation_tolerance_pct": DEVIATION_TOLERANCE_PCT,
        "heuristic_within_tolerance": None,
        "reason": (
            "transformers/sentencepiece not installed or BGE-M3 not cached — airgap mode. "
            "First Mac contributor with `pip install transformers sentencepiece` + "
            "`make models-bge` (BGE-M3 weights) re-runs to write MEASURED."
        ),
        "measurements": [
            {"sample": name, "chars": len(text), "tokens": None, "chars_per_token": None}
            for name, text in SAMPLE_TEXTS
        ],
    }


def _render_markdown(summary: dict[str, Any]) -> str:
    status = summary["status"]
    chars_per_token = summary["mean_chars_per_token"]
    measured = status == "MEASURED"
    rows: list[str] = []
    for m in summary["measurements"]:
        chars = m["chars"]
        tokens = m["tokens"] if m["tokens"] is not None else "—"
        ratio = m["chars_per_token"] if m["chars_per_token"] is not None else "—"
        rows.append(f"| {m['sample']} | {chars} | {tokens} | {ratio} |")
    table = "\n".join(rows)

    decision_line = (
        f"- heuristic_within_tolerance: {summary['heuristic_within_tolerance']}\n"
        f"- rag_chunk_target_chars locked at: 1500 (default)"
    )
    if measured and summary.get("heuristic_within_tolerance") is False:
        decision_line += (
            "\n- ACTION REQUIRED: deviation > tolerance — revisit chunker constants in Plan 04-02."
        )
    if not measured:
        airgap_note = summary.get("reason", "")
        decision_line += f"\n- airgap: {airgap_note}"

    return (
        f"---\n"
        f"phase: 04-hebrew-rag-knowledge-base\n"
        f"plan: 01\n"
        f"artifact: chunk-token-ratio-spike\n"
        f"status: {status}\n"
        f"chars_per_token: {chars_per_token}\n"
        f"sample_count: {summary['sample_count']}\n"
        f"---\n\n"
        f"# Hebrew Chunk → BGE-M3 Token Ratio — Spike Results\n\n"
        f"**Heuristic:** {HEURISTIC_CHARS_PER_TOKEN} chars/token (RESEARCH §Hebrew Chunking Strategy).\n"
        f"**Tolerance:** ±{DEVIATION_TOLERANCE_PCT}% before chunk size needs retuning.\n"
        f"**Status:** {status}"
        + (
            "\n\n## Per-sample measurement\n\n"
            f"| sample | chars | tokens | chars/token |\n"
            f"|--------|-------|--------|-------------|\n"
            f"{table}\n"
        )
        + (
            "\n## Decision\n"
            f"{decision_line}\n"
        )
    )


def _default_out_path() -> Path:
    # Walk up from this script to the repo root (where .planning/ lives).
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / ".planning").is_dir():
            return (
                parent
                / ".planning"
                / "phases"
                / "04-hebrew-rag-knowledge-base"
                / "04-01-SPIKE-RESULTS.md"
            )
    # Fallback: alongside the script.
    return here.parent / "04-01-SPIKE-RESULTS.md"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Wave-0 char→BGE-M3-token ratio spike (Plan 04-01).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help=(
            "Markdown output path (default: "
            ".planning/phases/04-hebrew-rag-knowledge-base/04-01-SPIKE-RESULTS.md)."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON summary on stdout. Markdown is still written unless --no-md.",
    )
    parser.add_argument(
        "--no-md",
        action="store_true",
        help="Skip writing the markdown artifact (useful for CI smoke).",
    )
    args = parser.parse_args(argv)

    out_path: Path = args.out if args.out is not None else _default_out_path()

    tok = _try_load_tokenizer()
    if tok is None:
        summary = _build_airgap_summary()
        print(
            "transformers/sentencepiece not installed or BGE-M3 not cached — "
            "airgap mode (UNMEASURED placeholder).",
            file=sys.stderr,
        )
    else:
        try:
            measurements = _measure_live(tok)
        except Exception as e:
            print(f"live measurement failed after tokenizer loaded: {e}", file=sys.stderr)
            return 1
        summary = _build_summary(measurements)

    if not args.no_md:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(_render_markdown(summary), encoding="utf-8")
        print(f"wrote {out_path}", file=sys.stderr)

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
