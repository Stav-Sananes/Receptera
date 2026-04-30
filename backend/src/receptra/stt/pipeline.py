"""WebSocket STT pipeline: VAD-gated incremental re-transcribe loop.

This module owns the live hot path for Phase 2 (STT-03 + STT-04). The
WebSocket handler at ``/ws/stt`` accepts binary 1024-byte int16 LE PCM
frames, runs them through the per-connection Silero VAD wrapper from
Plan 02-03, and emits typed pydantic events (``ready``, ``partial``,
``final``, ``error``) as JSON text frames.

Wire contract (RESEARCH §6 + §4.3):

* Client → server: binary frames, exactly 1024 bytes each, int16 LE,
  16 kHz mono, 32 ms per frame. Anything else is a protocol error.
* Server → client: JSON text frames, one event per frame, schema
  pinned by ``receptra.stt.events``.

Concurrency (Pitfall #5):

* ``WhisperModel.transcribe`` is synchronous C++ via CTranslate2. It
  MUST be wrapped in ``await asyncio.to_thread(...)`` so the event
  loop stays responsive. A regression test
  (``test_no_event_loop_blocking``) drives two concurrent WS through a
  slow-stub transcribe to prove the wrap is in place.

Per-connection isolation (Pitfall #2):

* A fresh ``StreamingVad`` is constructed per-connection, wrapping the
  shared ``app.state.vad_model`` singleton. ``vad.reset()`` is called
  in the ``finally`` block on cleanup — defense-in-depth against any
  cross-connection state leak via the iterator.

Architecture: ``run_utterance_loop`` is split out from
``websocket_stt_endpoint`` so Plan 02-06 (latency instrumentation) can
wrap the loop with metrics + audit-log inserts without rewriting the
FastAPI route decorator.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Awaitable, Callable

import numpy as np
from fastapi import WebSocket, WebSocketDisconnect
from loguru import logger
from numpy.typing import NDArray

from receptra.config import settings
from receptra.pipeline.audit import init_pipeline_db
from receptra.pipeline.hot_path import SuggestFn, make_suggest_fn
from receptra.pipeline.intent import detect_intent_and_send
from receptra.stt.audit import init_audit_db, insert_stt_utterance
from receptra.stt.engine import transcribe_hebrew
from receptra.stt.events import FinalTranscript, PartialTranscript, SttError, SttReady
from receptra.stt.metrics import (
    UtteranceMetrics,
    log_utterance,
    new_utterance_id,
    utc_now_iso,
)
from receptra.stt.vad import FRAME_BYTES, InvalidFrameError, StreamingVad
from receptra.supervisor.bus import bus as supervisor_bus

# RESEARCH §7 — Whisper quality degrades on <500 ms of audio. The first
# partial fires only once the speech buffer crosses this floor; below it
# the loop accumulates frames silently.
MIN_PARTIAL_AUDIO_MS = 500
INT16_MAX = 32768.0

# WebSocket close code 1007 = "Invalid frame payload data" (RFC 6455 §7.4.1).
# Used when the client sends a frame that violates the wire contract.
WS_CLOSE_INVALID_FRAME = 1007

TranscribeFn = Callable[[NDArray[np.float32]], Awaitable[str]]


def _frame_to_f32(frame_bytes: bytes) -> NDArray[np.float32]:
    """Decode a 1024-byte int16 LE frame to float32 in [-1.0, 1.0].

    Little-endian explicitly pinned via ``"<i2"`` (Pitfall #4) — using
    plain ``np.int16`` would honour native byte order, breaking the
    contract on big-endian hosts.
    """
    pcm_int16 = np.frombuffer(frame_bytes, dtype="<i2")
    return (pcm_int16.astype(np.float32) / INT16_MAX).copy()


def _now_ms() -> int:
    """Monotonic millisecond timestamp.

    Wall-clock APIs are forbidden in this module (verification gate) — only
    monotonic clocks are used so timestamps are not affected by NTP slew.
    """
    return int(time.monotonic() * 1000)


async def websocket_stt_endpoint(ws: WebSocket) -> None:
    """FastAPI WebSocket handler — accept, set up VAD + transcribe, drive loop.

    Construction of the per-connection ``StreamingVad`` wrapper happens
    here so the loop function below can be unit-tested without
    instantiating a FastAPI app. Cleanup (vad reset + socket close) is
    in the ``finally`` block.
    """
    await ws.accept()

    # Each WS connection = one agent session for the supervisor dashboard.
    # Honour ?agent_id=foo from the client (e.g. "agent-david"), otherwise
    # generate a random short id so multiple anonymous browsers don't collide.
    import uuid

    agent_id = ws.query_params.get("agent_id") or f"agent-{uuid.uuid4().hex[:8]}"
    from datetime import UTC
    from datetime import datetime as _dt
    await supervisor_bus.publish(
        {
            "type": "agent_connected",
            "agent_id": agent_id,
            "ts_utc": _dt.now(UTC).isoformat(),
        }
    )

    # T-02-06-06 — lazy idempotent SQLite init on every connection accept.
    # Cheap (single CREATE TABLE IF NOT EXISTS) and ensures the parent dir
    # exists before any insert runs. Wrapped in try/except so an audit-db
    # creation failure DOES NOT bring down the WS hot path.
    try:
        init_audit_db(settings.audit_db_path)
    except Exception as e:  # pragma: no cover — defensive
        logger.bind(event="stt.audit.init_failed").error(
            {"path": settings.audit_db_path, "err": str(e)}
        )
    # INT-05 — pipeline_runs table for hot_path audit. Same SQLite file,
    # idempotent CREATE TABLE IF NOT EXISTS.
    try:
        init_pipeline_db(settings.audit_db_path)
    except Exception as e:  # pragma: no cover — defensive
        logger.bind(event="pipeline.audit.init_failed").error(
            {"path": settings.audit_db_path, "err": str(e)}
        )

    whisper = ws.app.state.whisper
    vad_model = ws.app.state.vad_model

    # Model name surfaces to the client in the SttReady event so the
    # frontend can display "loaded model: <name>". Falls back to the
    # research-locked default when the stub does not declare a name.
    model_name = getattr(whisper, "model_name", "ivrit-ai/whisper-large-v3-turbo-ct2")

    await ws.send_json(SttReady(model=model_name).model_dump())

    vad = StreamingVad(
        model=vad_model,
        threshold=settings.vad_threshold,
        min_silence_ms=settings.vad_min_silence_ms,
        speech_pad_ms=settings.vad_speech_pad_ms,
    )

    async def transcribe(buffer: NDArray[np.float32]) -> str:
        # Pitfall #5 — synchronous C++ transcribe MUST run on a thread so
        # the event loop stays responsive for other connections + the
        # same connection's audio receive.
        text, _info = await asyncio.to_thread(transcribe_hebrew, whisper, buffer)
        return text

    # Phase 5 INT-01: build per-connection suggest callback from app.state.
    # Both embedder and chroma_collection may be None (INT-04 graceful degradation).
    embedder = getattr(ws.app.state, "embedder", None)
    chroma_collection = getattr(ws.app.state, "chroma_collection", None)
    suggest = make_suggest_fn(ws, embedder, chroma_collection, agent_id=agent_id)

    try:
        await run_utterance_loop(ws, vad, transcribe, suggest=suggest, agent_id=agent_id)
    except WebSocketDisconnect:
        logger.bind(event="stt.ws.disconnect").info({"msg": "client disconnected"})
    except Exception as e:  # pragma: no cover — defensive last-line catch
        logger.bind(event="stt.ws.error").exception({"msg": "unexpected error", "err": str(e)})
        with contextlib.suppress(Exception):
            await ws.send_json(SttError(code="model_error", message=str(e)).model_dump())
    finally:
        # Pitfall #2 — defensive reset on cleanup. The wrapper is local
        # to this connection so reset is technically redundant, but the
        # explicit call documents the per-connection isolation contract.
        vad.reset()
        with contextlib.suppress(Exception):
            await supervisor_bus.publish(
                {
                    "type": "agent_disconnected",
                    "agent_id": agent_id,
                    "ts_utc": _dt.now(UTC).isoformat(),
                }
            )
        with contextlib.suppress(Exception):  # already-closed paths
            await ws.close()


async def run_utterance_loop(
    ws: WebSocket,
    vad: StreamingVad,
    transcribe: TranscribeFn,
    *,
    suggest: SuggestFn | None = None,
    agent_id: str | None = None,
) -> None:
    """Drive the VAD-gated incremental re-transcribe loop on one connection.

    Pseudocode (RESEARCH §7):

        on VAD start: reset speech_buffer, mark t_speech_start
        on audio frame in active speech: append; maybe emit partial
        on VAD end: transcribe, emit final, [suggest], reset

    The function is split out from ``websocket_stt_endpoint`` so Plan
    02-06's metrics wrapper can call it with an instrumented
    ``transcribe`` callable that records per-call latency + writes an
    audit row, without touching the FastAPI route decorator.

    Phase 5 INT-02: after emitting ``FinalTranscript``, ``suggest`` is
    awaited (inline, not fire-and-forget) so the WS serialises cleanly.
    With ``suggest=None`` (unit tests that predate Phase 5), the loop
    behaves identically to the Phase 2 implementation.

    Args:
        ws: The accepted WebSocket. ``receive_bytes`` raises
            ``WebSocketDisconnect`` on client close — the caller handles
            that.
        vad: A fresh per-connection ``StreamingVad``.
        transcribe: An async callable wrapping the synchronous Whisper
            transcribe. The caller is responsible for putting the
            ``asyncio.to_thread`` wrap inside this callable; this
            function is therefore agnostic to the threadpool strategy
            (real to_thread, custom executor, or a sync fake in tests).
        suggest: Optional Phase 5 callback. If provided, called with
            ``(transcript_text, t_speech_end_ms, utterance_id)`` after
            every ``FinalTranscript``. None is safe — skips the pipeline.
    """
    speech_buffer: list[NDArray[np.float32]] = []
    t_speech_start_ms = 0
    audio_ms_at_last_partial = 0
    in_speech = False
    # Per-utterance audit state (STT-06). Reset on every VAD-start.
    utterance_id = ""
    partials_emitted = 0

    while True:
        frame = await ws.receive_bytes()

        try:
            event = vad.feed(frame)
        except InvalidFrameError as e:
            await ws.send_json(SttError(code="protocol_error", message=str(e)).model_dump())
            await ws.close(code=WS_CLOSE_INVALID_FRAME)
            return

        # Decode the frame ONCE — used both for buffer accumulation and
        # for the speech-start "first sample" capture.
        frame_f32 = _frame_to_f32(frame)
        now_ms = _now_ms()

        if event is not None and event["kind"] == "start":
            in_speech = True
            speech_buffer = [frame_f32]
            t_speech_start_ms = now_ms
            audio_ms_at_last_partial = 0
            # New utterance — fresh id + reset partial counter (STT-06).
            utterance_id = new_utterance_id()
            partials_emitted = 0
            continue

        if in_speech and event is None:
            # Mid-utterance frame — append + maybe emit a partial.
            speech_buffer.append(frame_f32)
            # Partial cadence is driven by ACCUMULATED AUDIO TIME, not
            # wall-clock time. In real-time streaming the two are roughly
            # equal (1 s wall ≈ 1 s audio buffered), so behaviour matches
            # RESEARCH §7's wall-clock pseudocode. But test-time clients
            # (and any non-real-time producer) burst frames at processing
            # speed — wall-clock gating would never fire. Audio-time
            # gating is also semantically correct: we want N partials per
            # utterance regardless of source playback rate.
            audio_samples = sum(s.shape[0] for s in speech_buffer)
            audio_ms = (audio_samples * 1000) // 16000
            audio_ms_since_partial = audio_ms - audio_ms_at_last_partial
            if (
                audio_ms_since_partial >= settings.stt_partial_interval_ms
                and audio_ms >= MIN_PARTIAL_AUDIO_MS
            ):
                combined = np.concatenate(speech_buffer)
                text = await transcribe(combined)
                await ws.send_json(
                    PartialTranscript(
                        text=text,
                        t_speech_start_ms=t_speech_start_ms,
                        t_emit_ms=_now_ms(),
                    ).model_dump()
                )
                audio_ms_at_last_partial = audio_ms
                partials_emitted += 1
            continue

        if event is not None and event["kind"] == "end" and in_speech:
            t_speech_end_ms = now_ms
            # Append the boundary frame so the final transcribe sees the
            # complete utterance (the "end" frame still contains audio
            # the VAD's speech_pad_ms wanted us to retain).
            speech_buffer.append(frame_f32)

            if not speech_buffer:  # pragma: no cover — defensive
                in_speech = False
                continue

            combined = np.concatenate(speech_buffer)
            duration_ms = (combined.shape[0] * 1000) // 16000

            t_transcribe_start_ms = _now_ms()
            text = await transcribe(combined)
            t_final_ready_ms = _now_ms()
            stt_latency_ms = max(0, t_final_ready_ms - t_speech_end_ms)
            transcribe_ms = max(0, t_final_ready_ms - t_transcribe_start_ms)

            await ws.send_json(
                FinalTranscript(
                    text=text,
                    t_speech_start_ms=t_speech_start_ms,
                    t_speech_end_ms=t_speech_end_ms,
                    stt_latency_ms=stt_latency_ms,
                    duration_ms=duration_ms,
                ).model_dump()
            )

            # Supervisor bus fan-out — non-blocking, dropped on slow subscriber.
            if agent_id:
                with contextlib.suppress(Exception):
                    await supervisor_bus.publish(
                        {
                            "type": "utterance_final",
                            "agent_id": agent_id,
                            "utterance_id": utterance_id,
                            "text": text,
                            "stt_latency_ms": stt_latency_ms,
                            "duration_ms": duration_ms,
                        }
                    )

            # STT-06 — emit per-utterance metrics + audit row AFTER the
            # final has reached the wire. log_utterance is in-process
            # (~µs), insert is sync sqlite3 (~ms). Both wrapped in
            # try/except: a logging or DB failure MUST NOT crash the WS
            # loop. T-02-06-03 — only completed utterances reach this
            # point, so half-written rows are impossible.
            metrics = UtteranceMetrics(
                utterance_id=utterance_id,
                ts_utc=utc_now_iso(),
                t_speech_start_ms=t_speech_start_ms,
                t_speech_end_ms=t_speech_end_ms,
                t_final_ready_ms=t_final_ready_ms,
                duration_ms=duration_ms,
                transcribe_ms=transcribe_ms,
                partials_emitted=partials_emitted,
                text=text,
                text_len_chars=len(text),
                wer_sample_id=None,
            )
            try:
                log_utterance(metrics)
            except Exception as e:  # pragma: no cover — defensive
                logger.bind(event="stt.metrics.log_failed").error(
                    {"utterance_id": utterance_id, "err": str(e)}
                )
            try:
                insert_stt_utterance(settings.audit_db_path, metrics)
            except Exception as e:
                logger.bind(event="stt.audit.insert_failed").error(
                    {"utterance_id": utterance_id, "err": str(e)}
                )

            # Phase 5 INT-02 + v1.1 F4: run suggest + intent detection in parallel.
            # asyncio.gather with return_exceptions=True ensures intent failure
            # never crashes the suggest pipeline (or vice versa).
            if suggest is not None:
                try:
                    results = await asyncio.gather(
                        suggest(text, t_speech_end_ms, utterance_id),
                        detect_intent_and_send(
                            text, ws, utterance_id, agent_id=agent_id
                        ),
                        return_exceptions=True,
                    )
                    for r in results:
                        if isinstance(r, BaseException):
                            logger.bind(event="pipeline.parallel_failed").warning(
                                {"utterance_id": utterance_id, "err": str(r)}
                            )
                except Exception as e:
                    logger.bind(event="pipeline.suggest_failed").error(
                        {"utterance_id": utterance_id, "err": str(e)}
                    )

            # Reset utterance state — the underlying VADIterator carries
            # silero's segmentation state across utterances on the same
            # connection. The loop continues to receive frames; subsequent
            # VAD-start events trigger a fresh utterance with a new id.
            # Verified by tests/stt/test_ws_pcm_roundtrip.py::
            # test_multi_utterance_emits_multiple_finals.
            speech_buffer = []
            in_speech = False
            t_speech_start_ms = 0
            utterance_id = ""
            partials_emitted = 0


# Re-export the constant module-readers expect to find here.
__all__ = ["FRAME_BYTES", "run_utterance_loop", "websocket_stt_endpoint"]
