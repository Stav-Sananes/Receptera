"""Shared fixtures for STT test package.

Provides a reusable ``mock_whisper_model`` fixture that matches the
``faster_whisper.WhisperModel.transcribe`` contract (segments iterable +
info object). Keeps STT tests fast and offline — never loads real weights.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

import pytest


@dataclass
class _SegStub:
    """Minimal stand-in for faster_whisper.transcribe.Segment."""

    text: str


@dataclass
class _InfoStub:
    """Minimal stand-in for faster_whisper.transcribe.TranscriptionInfo."""

    language: str = "he"
    language_probability: float = 0.98
    duration: float = 2.0


@pytest.fixture
def mock_whisper_model() -> MagicMock:
    """Return a Mock with ``.transcribe`` wired to a two-segment Hebrew reply.

    The mock's ``transcribe`` returns ``(segments_iterator, info)`` exactly as
    ``faster_whisper.WhisperModel.transcribe`` does, so ``transcribe_hebrew``
    can iterate + join + return. Tests can introspect ``call_args.kwargs`` to
    verify the locked-kwargs contract (RESEARCH §7).
    """
    model = MagicMock()

    def _transcribe(*_args: Any, **_kwargs: Any) -> tuple[Iterator[_SegStub], _InfoStub]:
        return iter([_SegStub(" שלום"), _SegStub(" עולם")]), _InfoStub()

    model.transcribe.side_effect = _transcribe
    return model
