"""Hebrew-aware WER/CER computation (STT-05, RESEARCH §9).

Pipeline: NFC normalize → strip niqqud + bidi → strip punctuation to whitespace
→ collapse whitespace.

Rationale:
* Hebrew reference transcripts often carry niqqud (vowel points) and
  cantillation marks that the model never outputs; comparing without
  stripping drives WER artificially high. Standard practice for Hebrew
  ASR eval (RESEARCH §9).
* Niqqud / cantillation are replaced with the EMPTY STRING (not whitespace)
  because they sit inside word forms — replacing with whitespace would
  shatter "שָׁלוֹם" into multiple "words" before WER counting.
* Punctuation IS replaced with a single space, so "שלום,מה" still scores as
  two distinct words after normalisation.
* Bidi control chars (LTR/RTL) are removed to empty string for the same
  intra-word reason.

WER computation uses ``jiwer.wer`` / ``jiwer.cer`` with their library
defaults (which apply ``ReduceToListOfListOfWords`` / -Chars under the
hood). RESEARCH §9 sketched a ``Compose([Strip(), RemoveMultipleSpaces()])``
pipeline; in jiwer 4.0 that compose alone is rejected because it does not
reduce to a list-of-list-of-words. Since ``normalise_hebrew`` already
strips and collapses whitespace, the jiwer-side transforms are redundant —
we let jiwer use its built-in defaults.
"""

from __future__ import annotations

import re
import unicodedata

import jiwer

# U+0591..U+05C7 covers Hebrew cantillation marks + all niqqud (vowel points).
# U+200E / U+200F are bidi control codepoints that some upstream transcripts
# inject to coerce LTR rendering of mixed-script content.
# Stripping to EMPTY STRING preserves intra-word integrity.
_HEBREW_INTRAWORD_RE = re.compile(r"[\u0591-\u05C7\u200E\u200F]")

# Punctuation is replaced with a single SPACE so that adjacent words remain
# distinct after normalisation (e.g. "שלום,מה" → "שלום מה").
_PUNCTUATION_RE = re.compile(r"[\.\,\!\?\:\;\"\'\(\)\[\]\-]")

_WHITESPACE_RE = re.compile(r"\s+")


def normalise_hebrew(text: str) -> str:
    """Canonical form for WER comparison.

    Pipeline: NFC normalize → strip niqqud + bidi (to empty) → strip
    punctuation (to space) → collapse whitespace → strip surrounding ws.
    """
    text = unicodedata.normalize("NFC", text)
    text = _HEBREW_INTRAWORD_RE.sub("", text)
    text = _PUNCTUATION_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text


def compute_wer(reference: str, hypothesis: str) -> dict[str, float]:
    """Return ``{"wer": float, "cer": float}`` with Hebrew normalisation.

    Both metrics are unit-range ``[0.0, 1.0+]`` (jiwer can exceed 1.0 when
    insertions outnumber the reference length). WER counts word errors; CER
    counts character errors. Hebrew is morphologically agglutinative, so CER
    is often the more robust signal — we report both per RESEARCH §9.

    Implementation note: ``normalise_hebrew`` is the pre-transform; jiwer's
    library-default transforms handle the post-tokenisation. See module
    docstring for why we don't pass our own jiwer Compose pipeline.
    """
    r = normalise_hebrew(reference)
    h = normalise_hebrew(hypothesis)
    wer = jiwer.wer(r, h)
    cer = jiwer.cer(r, h)
    return {"wer": float(wer), "cer": float(cer)}
