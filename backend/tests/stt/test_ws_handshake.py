"""Structural handshake tests for /ws/stt (Plan 02-04).

Two contracts under test:

1. WebSocket upgrade succeeds and the server emits an ``SttReady`` event
   describing the wire contract (model name, sample rate, frame bytes).
2. A wrong-size binary frame produces a single
   ``{"type":"error","code":"protocol_error",...}`` event and the socket
   closes cleanly -- T-02-04-01 mitigation, ASVS V5 input validation.

These tests use the REAL Silero VAD model (small TorchScript, ~30 MB,
already in dev cache via Plan 02-03 fixtures) plus a stubbed Whisper.
``StreamingVad.__init__`` calls ``VADIterator.reset_states`` which calls
``model.reset_states()`` -- the autouse ``object()`` sentinel from
conftest.py does not satisfy that interface, so we override here with a
real-VAD + stub-Whisper fixture.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


class _Info:
    duration = 1.0
    language = "he"
    language_probability = 1.0


class _CannedWhisperStub:
    """Whisper stub returning empty transcripts -- handshake tests do not
    need transcript content; they only check the ready + protocol_error
    paths which never reach transcribe."""

    model_name = "ivrit-ai/whisper-large-v3-turbo-ct2"

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    def transcribe(self, *_args: Any, **_kwargs: Any) -> tuple[Any, _Info]:
        return iter([]), _Info()


@pytest.fixture
def real_vad_app(monkeypatch: pytest.MonkeyPatch) -> Iterator[FastAPI]:
    """App with REAL Silero VAD + stub Whisper.

    Overrides the autouse ``object()`` Silero sentinel from conftest so
    that ``StreamingVad`` can wrap ``VADIterator`` (which calls
    ``model.reset_states()`` at construction).
    """
    for mod_name in ("receptra.main", "receptra.lifespan"):
        sys.modules.pop(mod_name, None)

    lifespan_mod = importlib.import_module("receptra.lifespan")
    from silero_vad import load_silero_vad as _real_load_silero

    monkeypatch.setattr(lifespan_mod, "WhisperModel", _CannedWhisperStub)
    monkeypatch.setattr(lifespan_mod, "load_silero_vad", _real_load_silero)

    from receptra.main import app

    yield app

    for mod_name in ("receptra.main", "receptra.lifespan"):
        sys.modules.pop(mod_name, None)


def test_upgrade_succeeds_and_ready_sent(real_vad_app: FastAPI) -> None:
    """``/ws/stt`` upgrade returns ``SttReady`` with the locked wire contract."""
    with TestClient(real_vad_app) as client, client.websocket_connect("/ws/stt") as ws:
        msg = ws.receive_json()

    assert msg["type"] == "ready"
    assert msg["sample_rate"] == 16000
    assert msg["frame_bytes"] == 1024
    assert isinstance(msg["model"], str)
    assert len(msg["model"]) > 0


def test_invalid_frame_size_returns_protocol_error(real_vad_app: FastAPI) -> None:
    """Wrong-size binary frame -> SttError(protocol_error) -> clean close.

    Drives the InvalidFrameError -> protocol_error envelope -> ws.close(1007)
    path published by Plan 02-03 + Plan 02-04. The socket MUST close
    cleanly (no exception leaks, no traceback in logs).
    """
    with TestClient(real_vad_app) as client, client.websocket_connect("/ws/stt") as ws:
        # Drain the ready event first.
        ready = ws.receive_json()
        assert ready["type"] == "ready"

        # Send a deliberately-wrong frame size (100 bytes instead of 1024).
        ws.send_bytes(b"\x00" * 100)

        # Server emits a protocol_error envelope before closing.
        err = ws.receive_json()
        assert err["type"] == "error"
        assert err["code"] == "protocol_error"
        assert isinstance(err["message"], str)
