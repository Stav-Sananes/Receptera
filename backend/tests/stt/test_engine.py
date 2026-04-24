"""Unit tests for ``receptra.stt.engine.transcribe_hebrew``.

These tests pin the Hebrew transcribe kwargs contract from RESEARCH §7 so any
drift (e.g., a future caller forgetting ``language='he'``) is caught by CI.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pytest

from receptra.config import Settings
from receptra.stt.engine import transcribe_hebrew


def test_transcribe_hebrew_locks_language_he(mock_whisper_model: MagicMock) -> None:
    """``language='he'`` MUST be passed on every call (ivrit-ai model card)."""
    audio = np.zeros(16000, dtype=np.float32)

    transcribe_hebrew(mock_whisper_model, audio)

    assert mock_whisper_model.transcribe.call_args.kwargs["language"] == "he"


def test_transcribe_hebrew_locks_all_params(mock_whisper_model: MagicMock) -> None:
    """Every locked kwarg from RESEARCH §7 MUST be present with exact value."""
    audio = np.zeros(16000, dtype=np.float32)

    transcribe_hebrew(mock_whisper_model, audio)

    kwargs: dict[str, Any] = mock_whisper_model.transcribe.call_args.kwargs
    assert kwargs["language"] == "he"
    assert kwargs["task"] == "transcribe"
    assert kwargs["beam_size"] == 1
    assert kwargs["best_of"] == 1
    assert kwargs["temperature"] == 0.0
    assert kwargs["condition_on_previous_text"] is False
    assert kwargs["vad_filter"] is False
    assert kwargs["without_timestamps"] is True
    assert kwargs["initial_prompt"] is None


def test_transcribe_hebrew_joins_segments(mock_whisper_model: MagicMock) -> None:
    """Two-segment response joins + strips to ``"שלום עולם"``."""
    audio = np.zeros(16000, dtype=np.float32)

    text, info = transcribe_hebrew(mock_whisper_model, audio)

    assert text == "שלום עולם"
    assert info["language"] == "he"
    assert info["duration"] == 2.0
    assert info["language_probability"] == 0.98


def test_transcribe_hebrew_rejects_non_float32(mock_whisper_model: MagicMock) -> None:
    """int16 audio MUST raise TypeError (Pitfall #4 defense)."""
    int16_audio = np.zeros(16000, dtype=np.int16)

    with pytest.raises(TypeError, match="float32"):
        transcribe_hebrew(mock_whisper_model, int16_audio)  # type: ignore[arg-type]

    # Model must not have been invoked at all when the dtype gate fails.
    mock_whisper_model.transcribe.assert_not_called()


def test_settings_new_fields_have_research_locked_defaults() -> None:
    """All 8 new STT-related Settings fields carry the research-locked defaults.

    ``stt_partial_interval_ms`` honors the value from 02-01-SPIKE-RESULTS.md
    (``partial_interval_decision``). Provisional lock: 700 ms (unmeasured path).
    Plan 02-06 replaces this with the M2-measured value before Phase 2 exits.
    """
    s = Settings()

    assert s.whisper_model_subdir == "whisper-turbo-ct2"
    assert s.whisper_compute_type == "int8"
    assert s.whisper_cpu_threads == 4
    assert s.vad_threshold == 0.5
    assert s.vad_min_silence_ms == 300
    assert s.vad_speech_pad_ms == 200
    assert s.audit_db_path == "./data/audit.sqlite"
    assert s.stt_partial_interval_ms in (700, 1000)
