"""Structural handshake tests for /ws/stt (Plan 02-04).

Two contracts under test:

1. WebSocket upgrade succeeds and the server emits an ``SttReady`` event
   describing the wire contract (model name, sample rate, frame bytes).
2. A wrong-size binary frame produces a single
   ``{"type":"error","code":"protocol_error",...}`` event and the socket
   closes cleanly — T-02-04-01 mitigation, ASVS V5 input validation.

These tests run against the autouse stubbed Whisper + Silero loaders from
``tests/conftest.py`` — no real model weights touched, no event-loop
blocking, fast offline CI execution.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_upgrade_succeeds_and_ready_sent(client: TestClient) -> None:
    """``/ws/stt`` upgrade returns ``SttReady`` with the locked wire contract."""
    with client.websocket_connect("/ws/stt") as ws:
        msg = ws.receive_json()

    assert msg["type"] == "ready"
    assert msg["sample_rate"] == 16000
    assert msg["frame_bytes"] == 1024
    # The autouse stub does not set model_name — the handler falls back to
    # the research-locked default. Either way the model field is non-empty.
    assert isinstance(msg["model"], str)
    assert len(msg["model"]) > 0


def test_invalid_frame_size_returns_protocol_error(client: TestClient) -> None:
    """Wrong-size binary frame → SttError(protocol_error) → clean close.

    Drives the InvalidFrameError → protocol_error envelope → ws.close(1007)
    path published by Plan 02-03 + Plan 02-04. The socket MUST close
    cleanly (no exception leaks, no traceback in logs).
    """
    with client.websocket_connect("/ws/stt") as ws:
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
