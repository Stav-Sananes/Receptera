**עברית** | [English](README.md)

<div dir="rtl" lang="he">

# Receptra

> פלטפורמת AI קולית עברית-ראשונה, בקוד פתוח ומתארחת עצמאית — לעסקים קטנים.

**ערך הליבה:** סוכן אנושי שעונה לשיחה בעברית על מחשב Mac מקבל הצעות רלוונטיות ומעוגנות במקורות תוך פחות משתי שניות — הכל רץ על המכונה שלו, ללא תלות בענן.

## סטטוס

אבן דרך 1 (MVP של קו-פיילוט בעברית) — בפיתוח פעיל. עדיין לא מוכן למשתמשי קצה.

## דרישות מוקדמות

- Apple Silicon Mac (M2 ומעלה, 16GB+ זיכרון מאוחד)
- Docker Desktop ל-Mac
- [Ollama](https://ollama.com) מותקן על המארח (`brew install ollama`)
- Node.js 22 LTS
- Python 3.12
- [uv](https://docs.astral.sh/uv/) לניהול תלויות Python
- כ-15 GB שטח פנוי על הדיסק

## התחלה מהירה

```bash
git clone <repo-url> receptra
cd receptra
cp .env.example .env
make setup
make up
```

## רישיון

Apache License 2.0. ראה [LICENSE](LICENSE).

</div>
