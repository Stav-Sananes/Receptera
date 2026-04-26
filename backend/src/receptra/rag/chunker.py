"""Hebrew-aware sentence + paragraph chunker (RAG-03, Plan 04-02).

Pure stdlib (re + unicodedata + dataclasses). RESEARCH §Hebrew Chunking
Strategy is the spec; tests/rag/test_chunker.py is the regression contract.

Pipeline::

    text → normalize_hebrew → split_paragraphs → split_sentences (per para)
         → greedy_pack (target_chars) → carry overlap → list[Chunk]

Char offsets are into the NORMALIZED text, not raw input — caller (Plan 04-04
ingest) is responsible for hashing the raw decoded UTF-8 for doc-id stability.

Hebrew-specific defenses (RESEARCH §Cluster 3):

* Gershayim (U+05F4 ״) and geresh (U+05F3 ׳) NEVER trigger sentence boundaries
  (Pitfall 2). The split regex ``[.!?]`` does NOT include them by construction.
* No capital-letter heuristic — Hebrew has no case (per hebrew-nlp-toolkit).
* English abbreviations (``Dr.``/``Mr.``/``vs.``/``etc.``/``e.g.``/``i.e.``/
  ``Inc.``/``Ltd.``/``Ph.D.``) are protected via re-glue: a "sentence" ending
  in one of these tails is glued back to the next.

normalize_hebrew DIVERGES from receptra.stt.wer.normalise_hebrew on punctuation:
the chunker PRESERVES ``.!?,:;`` because those drive sentence-boundary
detection. WER scorer collapses punctuation to whitespace because it scores
word-level edit distance. Both modules NFC-normalize and strip diacritics
identically.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from receptra.config import settings

# --- Public surface --------------------------------------------------------


@dataclass(frozen=True)
class Chunk:
    """One greedy-packed chunk of normalized Hebrew text.

    Attributes:
        chunk_index: 0-based ordinal in the source document's chunk stream.
        char_start: inclusive offset into the NORMALIZED text the chunk
            originated from. ``normalize_hebrew(raw)[char_start:char_end]``
            is closely related to ``text`` (modulo paragraph-join semantics
            documented above; the short-doc shortcut path slices exactly).
        char_end: exclusive offset; ``char_end - char_start`` may differ
            slightly from ``len(text)`` when paragraph boundaries collapse.
        text: the chunk body. Always non-empty for emitted chunks.
    """

    chunk_index: int
    char_start: int
    char_end: int
    text: str


# --- Hebrew + sentence regexes --------------------------------------------

# RESEARCH §Hebrew Chunking Strategy: U+0591..U+05C7 covers Hebrew
# cantillation marks + niqqud (vowel points). Phase 2 wer.py uses the same
# range; intentional divergence on punctuation handling is documented above.
_HEBREW_DIACRITICS = re.compile(r"[֑-ׇ]")

_PARA_END = re.compile(r"\n\s*\n+")
_SENT_END = re.compile(r"(?<=[.!?])\s+")

# English abbreviations whose period must NOT trigger a sentence split.
# Case-insensitive; word-boundary anchored. Hebrew gershayim/geresh do NOT
# appear here because [.!?] never includes them by construction.
_EN_ABBR_TAIL = re.compile(
    r"\b(?:Dr|Mr|Mrs|Ph\.D|vs|etc|e\.g|i\.e|Inc|Ltd)\.\s*$",
    re.IGNORECASE,
)


# --- Normalize -------------------------------------------------------------


def normalize_hebrew(text: str) -> str:
    """NFC + strip Hebrew diacritics + collapse intra-paragraph whitespace.

    Diverges from ``receptra.stt.wer.normalise_hebrew`` on punctuation: this
    preserves ``.!?,:;`` because the chunker needs them for sentence detection.

    Args:
        text: raw decoded UTF-8 input. May contain niqqud, mixed
            Hebrew/English, multiple paragraphs.

    Returns:
        NFC-normalized text with Hebrew diacritics stripped, intra-paragraph
        whitespace collapsed to single spaces, and paragraph breaks preserved
        as exactly ``\\n\\n``.
    """
    text = unicodedata.normalize("NFC", text)
    text = _HEBREW_DIACRITICS.sub("", text)
    # Collapse intra-paragraph runs of whitespace to a single space, BUT
    # preserve paragraph breaks (\n\n) so split_paragraphs can find them.
    paragraphs = _PARA_END.split(text)
    collapsed = [re.sub(r"\s+", " ", p).strip() for p in paragraphs]
    return "\n\n".join(p for p in collapsed if p)


# --- Split helpers ---------------------------------------------------------


def _split_paragraphs(text: str) -> list[str]:
    return [p for p in _PARA_END.split(text) if p.strip()]


def _split_sentences(paragraph: str) -> list[str]:
    """Split a paragraph on ``[.!?]\\s+`` and re-glue English abbreviations."""
    parts = _SENT_END.split(paragraph)
    glued: list[str] = []
    for p in parts:
        if glued and _EN_ABBR_TAIL.search(glued[-1]):
            # Re-glue: the previous "sentence" actually ended in an English
            # abbreviation (Dr., etc., ...) — NOT a real boundary.
            glued[-1] = glued[-1] + " " + p
        else:
            glued.append(p)
    return [s for s in glued if s.strip()]


# --- Chunking --------------------------------------------------------------


def chunk_hebrew(
    text: str,
    *,
    target_chars: int | None = None,
    overlap_chars: int | None = None,
) -> list[Chunk]:
    """Split Hebrew text into ~target_chars chunks at sentence boundaries.

    Args:
        text: raw decoded Hebrew (or mixed Hebrew/English) input.
        target_chars: chunk size in CHARACTERS of normalized text. Defaults
            to ``settings.rag_chunk_target_chars`` (1500).
        overlap_chars: trailing chars carried into the next chunk. Defaults
            to ``settings.rag_chunk_overlap_chars`` (200).

    Returns:
        list[Chunk] ordered by chunk_index. Empty list if input normalizes
        to empty.
    """
    target = (
        target_chars if target_chars is not None else settings.rag_chunk_target_chars
    )
    overlap = (
        overlap_chars
        if overlap_chars is not None
        else settings.rag_chunk_overlap_chars
    )

    normalized = normalize_hebrew(text)
    if not normalized:
        return []

    # Build the flat sentence stream across all paragraphs.
    units: list[str] = []
    for para in _split_paragraphs(normalized):
        units.extend(_split_sentences(para))
    if not units:
        return []

    # Single-doc-shorter-than-target shortcut — emit one chunk that exactly
    # covers the normalized text (offsets satisfy normalized[s:e] == text).
    if len(normalized) <= target:
        return [
            Chunk(
                chunk_index=0,
                char_start=0,
                char_end=len(normalized),
                text=normalized,
            )
        ]

    chunks: list[Chunk] = []
    cur_units: list[str] = []
    cur_len = 0
    cursor = 0  # running offset into the normalized text for char_start

    def emit() -> None:
        nonlocal cur_units, cur_len, cursor
        if not cur_units:
            return
        chunk_text = " ".join(cur_units)
        char_start = cursor
        char_end = char_start + len(chunk_text)
        chunks.append(
            Chunk(
                chunk_index=len(chunks),
                char_start=char_start,
                char_end=char_end,
                text=chunk_text,
            )
        )
        # Carry overlap: keep tail sentences whose total length <= overlap.
        if overlap <= 0:
            cur_units = []
            cur_len = 0
            cursor = char_end
            return
        tail_chars = 0
        tail_units: list[str] = []
        for u in reversed(cur_units):
            # Always keep at least one tail unit (so chunk[N+1] starts with
            # the last sentence of chunk[N]); break once we exceed budget.
            if tail_chars + len(u) + 1 > overlap and tail_units:
                break
            tail_units.insert(0, u)
            tail_chars += len(u) + 1
        cur_units = tail_units
        cur_len = sum(len(u) + 1 for u in cur_units)
        cursor = char_end - tail_chars  # overlap window begins here

    for u in units:
        # If adding this unit would exceed target AND we already have content,
        # emit the current chunk first (with its overlap carry).
        if cur_len + len(u) + 1 > target and cur_units:
            emit()

        # Defensive: a single unit (e.g. one >target Hebrew word) cannot be
        # split further at sentence level. Emit it as a SOLE-UNIT chunk
        # (no overlap carry — the unit IS the chunk) and continue. Prevents
        # infinite loop AND duplicate emission on pathological inputs
        # (Pitfall 8 / DoS / T-04-02-01).
        if len(u) > target:
            cur_units.append(u)
            chunk_text = u
            char_start = cursor
            char_end = char_start + len(chunk_text)
            chunks.append(
                Chunk(
                    chunk_index=len(chunks),
                    char_start=char_start,
                    char_end=char_end,
                    text=chunk_text,
                )
            )
            cur_units = []
            cur_len = 0
            cursor = char_end
            continue

        cur_units.append(u)
        cur_len += len(u) + 1

    if cur_units:
        emit()

    return chunks


__all__ = ["Chunk", "chunk_hebrew", "normalize_hebrew"]
