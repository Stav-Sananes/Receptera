"""Unit tests for Hebrew WER normalization + jiwer wrapper (STT-05, Plan 02-05).

Tests the contract from PLAN.md task 1 behavior block:

- NFC normalization (NFD-decomposed input must produce decomposition-free
  output once niqqud is stripped).
- Niqqud + cantillation stripped (range U+0591..U+05C7).
- Common Hebrew punctuation stripped to whitespace (so word boundaries are
  preserved when punctuation glues two words).
- Bidi control chars (U+200E LTR, U+200F RTL) removed.
- Multiple whitespace collapsed.
- compute_wer end-to-end matches expected values for identical, near-identical
  (punctuation-only diff), one-word-substitution, and empty-hypothesis cases.
"""

from __future__ import annotations

import unicodedata

from receptra.stt.wer import compute_wer, normalise_hebrew


def test_nfc_normalization() -> None:
    """NFD-decomposed Hebrew text round-trips through normalise_hebrew with no
    combining marks left behind."""
    nfd = unicodedata.normalize("NFD", "שָׁלוֹם")
    out = normalise_hebrew(nfd)
    # No combining marks (niqqud range) should remain after normalisation.
    for ch in out:
        assert not (0x0591 <= ord(ch) <= 0x05C7), (
            f"combining mark U+{ord(ch):04X} survived normalise_hebrew on NFD input"
        )
    # Output is in NFC (idempotent under NFC).
    assert out == unicodedata.normalize("NFC", out)


def test_niqqud_stripped() -> None:
    """Plain niqqud-bearing word reduces to the bare consonant skeleton."""
    out = normalise_hebrew("שָׁלוֹם")
    assert out == "שלום"


def test_punctuation_stripped() -> None:
    """Common punctuation is replaced by whitespace and then collapsed."""
    out = normalise_hebrew("שלום, מה שלומך?")
    assert out == "שלום מה שלומך"


def test_bidi_control_chars_stripped() -> None:
    """LTR + RTL bidi control chars are removed without inserting whitespace.

    The two surrounding tokens butt up against each other after stripping —
    consistent with how WER normalisation should treat invisible formatting.
    """
    out = normalise_hebrew("שלום\u200eworld\u200f")
    assert "\u200e" not in out
    assert "\u200f" not in out
    assert "שלום" in out
    assert "world" in out


def test_whitespace_collapsed() -> None:
    """Internal runs of whitespace + tabs + newlines collapse to a single
    space, and surrounding whitespace is stripped."""
    out = normalise_hebrew("שלום   \t  עולם\n")
    assert out == "שלום עולם"


def test_compute_wer_identical() -> None:
    """Two identical strings yield 0.0 WER and 0.0 CER."""
    metrics = compute_wer("שלום עולם", "שלום עולם")
    assert metrics["wer"] == 0.0
    assert metrics["cer"] == 0.0


def test_compute_wer_one_word_off() -> None:
    """Trailing punctuation in the hypothesis is normalised away — zero error."""
    metrics = compute_wer("שלום עולם", "שלום עולם!")
    assert metrics["wer"] == 0.0
    assert metrics["cer"] == 0.0


def test_compute_wer_substitution() -> None:
    """One-word substitution → WER 0.5; CER smaller than WER (per-char distance
    on a 4-char vs 4-char-ish swap is bounded by character count, not word count)."""
    metrics = compute_wer("שלום עולם", "שלום חבר")
    assert metrics["wer"] == 0.5
    assert 0.0 < metrics["cer"] < 0.5


def test_compute_wer_empty_hypothesis() -> None:
    """Empty hypothesis vs N-word reference is 1.0 WER (total deletion)."""
    metrics = compute_wer("שלום עולם", "")
    assert metrics["wer"] == 1.0
