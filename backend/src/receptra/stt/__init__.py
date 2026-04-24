"""Hebrew streaming speech-to-text subsystem.

Exposes ``transcribe_hebrew`` — the single-source-of-truth wrapper for every
``faster_whisper.WhisperModel.transcribe`` call in the project. All live and
batch STT paths MUST flow through this module so Hebrew params (RESEARCH §7)
can never drift across call sites.
"""

from receptra.stt.engine import transcribe_hebrew

__all__ = ["transcribe_hebrew"]
