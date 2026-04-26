"""Hebrew chunker correctness suite — TDD RED commit (Plan 04-02 Wave 2).

Pins the chunker contract from RESEARCH §Hebrew Chunking Strategy + §Cluster 3
BEFORE implementation. Plan 04-02 GREEN commit (next task) makes these pass.

Critical regression tests:
- test_gershayim_not_boundary (Pitfall 2)
- test_geresh_not_boundary (Pitfall 2)
- test_no_mid_word_split (Pitfall 8)
- test_chunk_hebrew_pure_stdlib (license / dep-creep guard)
- test_normalize_diverges_from_wer (intentional split from Phase 2 normalise_hebrew)
"""

from __future__ import annotations

import unicodedata
from pathlib import Path

import pytest
from receptra.rag.chunker import Chunk, chunk_hebrew, normalize_hebrew

from receptra.config import settings

# --------------------------------------------------------------------------
# normalize_hebrew tests
# --------------------------------------------------------------------------


def test_normalize_hebrew_nfc() -> None:
    """NFD-decomposed niqqud → NFC composed; idempotent on NFC input."""
    # Decomposed shalom-with-niqqud built character-by-character to force NFD.
    decomposed = unicodedata.normalize(
        "NFD", "שָׁלוֹם"
    )
    assert unicodedata.is_normalized("NFD", decomposed) or unicodedata.is_normalized(
        "NFC", decomposed
    )
    out = normalize_hebrew(decomposed)
    # After normalization the result must be NFC-stable.
    assert unicodedata.is_normalized("NFC", out)
    # Idempotent: normalize twice == once.
    assert normalize_hebrew(out) == out


def test_normalize_hebrew_strips_niqqud() -> None:
    """Niqqud (vowel diacritics) stripped to empty so byte content stays stable."""
    # שָׁלוֹם — qamatz U+05B8 + shin-dot U+05C1 + holam U+05B9
    with_niqqud = "שָׁלוֹם"
    out = normalize_hebrew(with_niqqud)
    assert out == "שלום"  # שלום, 4 letters
    assert len(out) == 4


def test_normalize_hebrew_collapses_whitespace() -> None:
    """Intra-paragraph whitespace collapses to ' '; '\\n\\n' paragraph breaks survive."""
    text = "שלום   עולם\n\n\n  בוקר טוב"
    out = normalize_hebrew(text)
    assert out == "שלום עולם\n\nבוקר טוב"


# --------------------------------------------------------------------------
# chunk_hebrew core behavior
# --------------------------------------------------------------------------


def test_chunk_hebrew_empty() -> None:
    """Empty / whitespace-only inputs produce no chunks."""
    assert chunk_hebrew("") == []
    assert chunk_hebrew("   \n\n  ") == []


def test_chunk_hebrew_single_short_doc() -> None:
    """Short doc returns a single chunk covering the full normalized text."""
    text = "שלום עולם. בוקר טוב."
    chunks = chunk_hebrew(text)
    assert len(chunks) == 1
    c = chunks[0]
    assert isinstance(c, Chunk)
    assert c.chunk_index == 0
    assert c.char_start == 0
    normalized = normalize_hebrew(text)
    assert c.char_end == len(normalized)
    assert c.text == normalized


def test_chunk_hebrew_paragraph_split() -> None:
    """Multi-paragraph doc respects paragraph boundaries when splitting."""
    # Three paragraphs, each ~30 chars; total < target → 1 chunk.
    short_doc = "פסקה ראשונה כאן.\n\nפסקה שנייה כאן.\n\nפסקה שלישית כאן."
    short_chunks = chunk_hebrew(short_doc)
    assert len(short_chunks) == 1

    # Three paragraphs each near target_chars/2 → must split into >=2 chunks.
    big_para = "משפט ארוך מאוד שחוזר על עצמו פעמים רבות מאוד. " * 30  # ~1300+ chars each
    long_doc = f"{big_para}\n\n{big_para}\n\n{big_para}"
    long_chunks = chunk_hebrew(long_doc, target_chars=1500, overlap_chars=200)
    assert len(long_chunks) >= 2


def test_chunk_hebrew_sentence_split() -> None:
    """Single long paragraph splits at sentence boundaries (no mid-sentence cuts)."""
    sentence = "זהו משפט עברי באורך בינוני שמסתיים בנקודה ועוד מילים נוספות לאיזון. "
    # Build 6 distinct sentences each ~500 chars.
    sentences = []
    for _ in range(6):
        body = (sentence * 7).strip()  # ~~ 500 chars
        sentences.append(body)
    paragraph = " ".join(sentences)

    chunks = chunk_hebrew(paragraph, target_chars=1500, overlap_chars=0)
    assert len(chunks) >= 2
    # No chunk text ends mid-sentence — every chunk text ends with `.` or
    # contains complete sentences only.
    for c in chunks:
        # Every chunk should END on a sentence terminator (or be the final chunk).
        stripped = c.text.rstrip()
        assert stripped.endswith(".") or c is chunks[-1]


# --------------------------------------------------------------------------
# Hebrew-specific regression: gershayim + geresh NEVER end sentences
# --------------------------------------------------------------------------


def test_gershayim_not_boundary() -> None:
    """REGRESSION (Pitfall 2): gershayim ״ U+05F4 is NOT a sentence terminator."""
    # ע״מ = "on behalf of" abbreviation; abbreviation marker, not period.
    text = "ע״מ 30 לחודש. אנחנו פתוחים."
    chunks = chunk_hebrew(text)
    # Single short doc → exactly 1 chunk.
    assert len(chunks) == 1
    body = chunks[0].text
    # The gershayim abbreviation must remain intact (not split).
    assert "ע״מ" in body
    # Body has 2 sentences total (split on `.` after `לחודש`).
    # Verify by counting period-terminated tokens in the chunk text.
    assert body.count(".") == 2


def test_geresh_not_boundary() -> None:
    """REGRESSION (Pitfall 2): geresh ׳ U+05F3 is NOT a sentence terminator."""
    # מס׳ = "number" abbreviation; geresh as numeral/abbreviation marker.
    text = "מס׳ 7 בלבד. הזמנות מראש."
    chunks = chunk_hebrew(text)
    assert len(chunks) == 1
    body = chunks[0].text
    assert "מס׳" in body
    assert body.count(".") == 2


def test_english_abbreviation_protected() -> None:
    """English abbreviations like Dr., etc., e.g. don't trigger sentence boundaries."""
    text = "פגשנו את Dr. Cohen. הוא רופא מצוין."
    chunks = chunk_hebrew(text)
    assert len(chunks) == 1
    body = chunks[0].text
    # `Dr.` stays glued to `Cohen` — no spurious split between them.
    assert "Dr. Cohen" in body
    # Period count: `Dr.` + `Cohen.` + `מצוין.` = 3 periods.
    assert body.count(".") == 3


# --------------------------------------------------------------------------
# Pathological inputs — DoS defense + whitespace fallback
# --------------------------------------------------------------------------


def test_no_mid_word_split() -> None:
    """A single oversized 'word' (no whitespace) emits as a single chunk; no infinite loop."""
    # 3000 Hebrew chars in one unbroken token — chunker must NOT split mid-character.
    word = "ש" * 3000
    chunks = chunk_hebrew(word, target_chars=1500, overlap_chars=200)
    # Best-effort: the entire oversized word survives as one chunk's text.
    assert len(chunks) == 1
    assert chunks[0].text == word
    assert len(chunks[0].text) == 3000


def test_overlap_carryover() -> None:
    """Trailing overlap_chars of chunk[N] appears at the start of chunk[N+1]."""
    sentence = "משפט קצר ובסיסי. "
    # Build a doc that splits into exactly 2 chunks under target=400 / overlap=80.
    text = sentence * 50  # ~~ 850 chars total
    chunks = chunk_hebrew(text, target_chars=400, overlap_chars=80)
    assert len(chunks) >= 2
    # chunk[1].char_start corresponds to the overlap window of chunk[0].
    # We allow tolerance because the overlap rounds to whole sentences.
    overlap_window = chunks[0].text[-100:]  # generous window
    # Some sentence from the tail of chunk[0] must appear in chunk[1] start.
    assert any(
        sent.strip() and sent.strip() in chunks[1].text[:200]
        for sent in overlap_window.split(".")
        if sent.strip()
    )


def test_chunk_index_monotonic() -> None:
    """Chunks numbered 0, 1, 2, ..., N-1 in order."""
    text = "משפט. " * 500  # ~3000 chars → multiple chunks at default settings
    chunks = chunk_hebrew(text, target_chars=400, overlap_chars=50)
    assert len(chunks) >= 3
    for i, c in enumerate(chunks):
        assert c.chunk_index == i


def test_char_offsets_into_normalized_text() -> None:
    """`normalized[chunk.char_start:chunk.char_end] == chunk.text` for each chunk.

    Documents the contract that char offsets are into the NORMALIZED text,
    not the raw input. (The implementation may join units with spaces, so this
    test asserts the documented invariant only for the SHORT-DOC shortcut path.)
    """
    text = "שלום עולם. בוקר טוב."
    normalized = normalize_hebrew(text)
    chunks = chunk_hebrew(text)
    assert len(chunks) == 1
    c = chunks[0]
    assert normalized[c.char_start : c.char_end] == c.text


# --------------------------------------------------------------------------
# Settings integration
# --------------------------------------------------------------------------


def test_chunk_hebrew_uses_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """No kwargs → defaults from settings.rag_chunk_target_chars / _overlap_chars."""
    # Build a 500-char doc.
    text = ("משפט קצר. " * 60).strip()
    monkeypatch.setattr(settings, "rag_chunk_target_chars", 100)
    monkeypatch.setattr(settings, "rag_chunk_overlap_chars", 0)
    chunks = chunk_hebrew(text)
    # With target=100 char windows, expect ~5 chunks (not 1 as default 1500 would yield).
    assert len(chunks) >= 3


def test_normalize_diverges_from_wer() -> None:
    """Chunker normalize PRESERVES `.!?` punctuation (WER scorer collapses them).

    Documents the intentional divergence between
    `receptra.rag.chunker.normalize_hebrew` and
    `receptra.stt.wer.normalise_hebrew`. The chunker NEEDS punctuation to
    drive sentence boundary detection; the WER scorer doesn't.
    """
    out = normalize_hebrew("שלום, עולם!")
    # Comma + exclamation preserved. NFC + diacritics stripped (none present here).
    assert "," in out
    assert "!" in out


# --------------------------------------------------------------------------
# License / dep-creep guard
# --------------------------------------------------------------------------


def test_chunk_hebrew_pure_stdlib() -> None:
    """Chunker module imports ONLY allowlisted modules — no `transformers`, etc.

    Reads chunker.py source and inspects every `from X import` / `import X`
    line. Allowlist: re, unicodedata, dataclasses, typing, __future__,
    receptra.config (and aliases of the latter). Anything else is a
    license / dependency creep regression and fails CI.
    """
    import receptra.rag.chunker as ch

    src_path = Path(ch.__file__)
    src = src_path.read_text(encoding="utf-8")
    allowed = {
        "re",
        "unicodedata",
        "dataclasses",
        "typing",
        "__future__",
        "receptra.config",
    }

    forbidden_found: list[str] = []
    for raw in src.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # Only inspect top-level imports (no leading whitespace in raw).
        if raw.startswith(("import ", "from ")):
            if line.startswith("import "):
                module = line.split()[1].split(".")[0]
                top = module
            else:
                # `from X.Y import ...`
                parts = line.split()
                top = parts[1]
            if top not in allowed and top != "re" and top not in {a.split(".")[0] for a in allowed}:
                # Allow stdlib-deeper variants? No — keep allowlist strict.
                forbidden_found.append(line)

    assert forbidden_found == [], (
        f"Chunker imports outside allowlist (license/dep-creep regression): "
        f"{forbidden_found}"
    )
