---
phase: "02-hebrew-streaming-stt"
plan: "02-03"
subsystem: stt
tags: [stt, vad, silero, streaming, per-connection, websocket-prep]
requires:
  - "Plan 02-01: silero-vad 6.2.1 pinned in backend/pyproject.toml + uv.lock"
  - "Plan 02-02: app.state.vad_model singleton (raw Silero TorchScript model) loaded onto app.state in the lifespan asynccontextmanager"
  - "Plan 02-02: settings.vad_threshold=0.5, settings.vad_min_silence_ms=300, settings.vad_speech_pad_ms=200 (research-locked defaults)"
provides:
  - "backend/src/receptra/stt/vad.py — StreamingVad class wrapping silero_vad.VADIterator per WebSocket connection"
  - "StreamingVad(model, threshold, min_silence_ms, speech_pad_ms) — constructor taking a shared Silero model + per-connection segmentation params"
  - "StreamingVad.feed(frame_bytes: bytes) -> VadEvent | None — consume one 1024-byte int16 LE frame, return typed event or None"
  - "StreamingVad.reset() -> None — clear per-session VADIterator state (between utterances or on reconnect)"
  - "VadEvent TypedDict — {kind: 'start'|'end', t_ms: int} normalized from Silero's seconds-float output"
  - "InvalidFrameError(ValueError) — raised before any numpy allocation when frame length != 1024 bytes"
  - "Wire-format constants FRAME_BYTES=1024, FRAME_SAMPLES=512, SAMPLE_RATE_HZ=16000 — exported for Plan 02-04 to validate WebSocket binary frames against the same contract"
affects:
  - "Plan 02-04 (/ws/stt WebSocket endpoint): instantiates a StreamingVad PER connection wrapping app.state.vad_model; converts InvalidFrameError to {type:'error',code:'protocol_error'} envelope; reuses FRAME_BYTES constant for incoming-frame size validation"
  - "Plan 02-06 (latency instrumentation + audit log): VadEvent t_ms timestamps feed the per-utterance latency log; speech-start to first-partial-transcript is the headline metric"
tech-stack:
  added:
    - "silero_vad.VADIterator wrapped per-connection (replaces faster-whisper's built-in vad_filter — RESEARCH §4 mandates external VADIterator)"
  patterns:
    - "Per-connection state isolation: each WebSocket handler constructs its own StreamingVad wrapping the SHARED Silero model singleton; the iterator carries per-session state but the model weights are loaded once at app startup (Pitfall #2 mitigation)"
    - "Wire-format validation at module boundary: feed() raises InvalidFrameError before allocating numpy arrays so malformed input cannot reach the model (T-02-03-01 / ASVS V5)"
    - "Explicit little-endian int16 pin: dtype='<i2' (not dtype=np.int16, which honors native byte order) so the wire contract holds on any host architecture (Pitfall #4 partial defense; full validation lives in Plan 02-04 wire layer)"
    - "Settings-decoupled construction: StreamingVad accepts threshold/min_silence_ms/speech_pad_ms as constructor args, not via Settings import — keeps the class trivially testable and lets Plan 02-04 wire config at the WebSocket entry point"
    - "Stateless test signal synthesis: voiced-frame helper seeds its noise component by phase (not via a stateful module-level RNG) so test ordering is irrelevant — required for the per-instance state-isolation regression to be deterministic"
key-files:
  created:
    - "backend/src/receptra/stt/vad.py"
    - "backend/tests/stt/test_vad_streaming.py"
    - ".planning/phases/02-hebrew-streaming-stt/02-03-SUMMARY.md"
  modified: []
key-decisions:
  - "StreamingVad wraps an ALREADY-LOADED model passed via constructor — does NOT call load_silero_vad itself. Decouples this module from the Plan 02-02 lifespan, makes unit tests self-contained, and matches the canonical FastAPI pattern of dependency-injecting singletons from app.state."
  - "Frame size is validated as EXACTLY 1024 bytes (no buffering of partial frames inside StreamingVad). Per RESEARCH §6 + Pitfall #4, frame fragmentation is a client-side concern (Phase 6 frontend); the backend treats it as a wire-protocol error."
  - "VADIterator constructed once per StreamingVad and reset_states() is called BOTH in __init__ AND in the public reset() method. Belt-and-braces guard against the silero_vad API ever leaking state from a recycled iterator (Pitfall #2)."
  - "BE byte-order is documented as silently mis-decoded (test_int16_le_byte_order_enforced asserts feed() returns None or a VadEvent without raising). Byte-order validation belongs at the WebSocket protocol layer (Plan 02-04), not inside this utility class. Documented as accept-disposition T-02-03-03 (no security impact in local-only single-user threat model)."
  - "Test signal upgraded from 1 kHz pure tone to FM-modulated harmonic stack with AM envelope and broadband noise. Pure sinusoids do not register as speech to Silero (peak prob ~0.2); the speech-like synthesizer reliably crosses 0.9. This sidesteps bundling a recorded WAV asset into the test suite while still exercising the real Silero model end-to-end."
metrics:
  duration: "~4 min"
  tasks_completed: "1/1"
  files_created: 3
  files_modified: 0
  tests_added: 7
  completed: "2026-04-25"
threat_flags: []
---

# Phase 2 Plan 02-03: Per-Connection Silero VAD Streaming Wrapper Summary

`StreamingVad` — a per-WebSocket-connection wrapper around `silero_vad.VADIterator` that accepts 1024-byte int16 LE PCM frames, isolates segmentation state per connection (Pitfall #2 regression-guarded), and emits typed `{kind, t_ms}` speech-boundary events for Plan 02-04's WebSocket handler to consume.

## STT-02 Satisfied

> **STT-02:** Silero VAD identifies speech chunks from an incoming PCM audio stream.

How:
- `backend/src/receptra/stt/vad.py` exposes `StreamingVad(model, threshold, min_silence_ms, speech_pad_ms)` — a thin per-connection wrapper around `silero_vad.VADIterator`.
- `feed(frame_bytes)` consumes one 1024-byte int16 LE frame (the wire-format contract from RESEARCH §6), converts to float32 via `np.frombuffer(buf, dtype="<i2").astype(np.float32) / 32768.0`, and returns either `None` (no boundary crossed) or `{kind: 'start' | 'end', t_ms: int}`.
- The 512-sample window mandated by Silero v5+ (RESEARCH §4.3) is enforced exactly — `InvalidFrameError` is raised on any other length BEFORE allocating the numpy buffer (T-02-03-01 mitigation).
- `reset_states()` is called both in `__init__` and in the public `reset()` method, guarding against any future iterator-recycling regression (Pitfall #2).

## Published Contract for Plan 02-04

Plan 02-04 (`/ws/stt` WebSocket endpoint) consumes:

```python
from receptra.stt.vad import (
    FRAME_BYTES,        # 1024 — wire-format size guard
    FRAME_SAMPLES,      # 512  — Silero v5+ mandatory window
    SAMPLE_RATE_HZ,     # 16000
    InvalidFrameError,  # convert to {"type": "error", "code": "protocol_error"} envelope
    StreamingVad,
    VadEvent,
)

# Per-connection construction inside the WebSocket handler:
vad = StreamingVad(
    model=app.state.vad_model,                  # shared Silero singleton from 02-02 lifespan
    threshold=settings.vad_threshold,           # 0.5
    min_silence_ms=settings.vad_min_silence_ms, # 300
    speech_pad_ms=settings.vad_speech_pad_ms,   # 200
)

while True:
    frame = await ws.receive_bytes()
    try:
        event = vad.feed(frame)
    except InvalidFrameError:
        await ws.send_json({"type": "error", "code": "protocol_error"})
        await ws.close()
        return
    if event is not None:
        if event["kind"] == "start":
            ...  # begin accumulating audio buffer
        else:  # "end"
            ...  # flush buffer through transcribe_hebrew()
```

## Wire-Format Constants

`FRAME_BYTES`, `FRAME_SAMPLES`, and `SAMPLE_RATE_HZ` are module-level constants importable by Plan 02-04 so the WebSocket entry point and the VAD wrapper share a single source of truth for the wire contract. Plan 02-04 will also use `FRAME_BYTES` for the per-frame size guard at the WebSocket boundary (defense in depth — both layers reject malformed frames).

## Verification

All 6 plan-verification gates pass:

1. `uv run ruff check src/receptra/stt/vad.py tests/stt/test_vad_streaming.py` — 0 exit
2. `uv run mypy src/receptra/stt/vad.py` — 0 exit (Success: no issues found in 1 source file)
3. `uv run pytest tests/stt/test_vad_streaming.py -xvs` — 7 passed (frame-size guard, silence, voiced-burst start, voiced→silence end, two-instance state isolation, reset, BE-byte-order tolerance)
4. `grep -q 'dtype="<i2"' backend/src/receptra/stt/vad.py` — 0 exit (little-endian explicitly pinned)
5. `grep -c "reset_states" backend/src/receptra/stt/vad.py` — 2 (constructor + reset method)
6. `grep -q "FRAME_BYTES = 1024" backend/src/receptra/stt/vad.py` — 0 exit

Full backend suite remains green: 19/19 tests (5 engine + 4 lifespan + 7 vad + 3 healthz). mypy strict clean across all 16 source files.

## Threat Mitigations

| Threat ID  | Mitigation status | Evidence |
|------------|-------------------|----------|
| T-02-03-01 (DoS via malformed frame size) | mitigated | `feed()` raises `InvalidFrameError` before numpy allocation. `test_invalid_frame_size_raises` covers 1000 / 1028 / 0 byte inputs. |
| T-02-03-02 (Cross-connection VAD state leak — Pitfall #2) | mitigated | Per-connection `StreamingVad` instance; each constructs its own `VADIterator`. `test_two_instances_have_independent_state` regression-guard: drives instance A into active speech, then feeds 40 silence frames to instance B and asserts B emits no events. |
| T-02-03-03 (BE byte-order tampering) | accepted | Documented in `test_int16_le_byte_order_enforced`. Garbled audio fails to produce meaningful transcripts but does not crash. No security impact in local-only single-user threat model (RESEARCH Security non-goals). |
| T-02-03-04 (DoS via abusive frame rate) | transferred to Plan 02-04 | Per-connection rate limiting is a WebSocket-handler concern, explicitly out of scope for this utility class. |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test signal synthesizer upgraded from pure tone to FM-modulated speech-like stack**

- **Found during:** Task 1 GREEN phase (initial test run)
- **Issue:** The plan-suggested 1 kHz sine helper produced raw Silero speech-probabilities of only ~0.2 (well below the 0.5 threshold). `test_tone_burst_produces_start_event` failed with no `start` events fired. Silero v5 is trained on real speech and treats static harmonic content as silence.
- **Fix:** Rewrote `_voiced_frame()` as a formant-FM synthesizer: pitch-wobble at ~130 Hz mean (±30 Hz at 4 Hz vibrato), 8-harmonic stack with FM-integrated phase, 5 Hz syllable-rate AM envelope, and 0.15-amplitude broadband noise for breath-like content. Reliably drives Silero above 0.9. The `_tone_frame()` symbol referenced in the plan was renamed to `_voiced_frame()` and the docstring rewritten to explain why pure sinusoids don't work.
- **Files modified:** `backend/tests/stt/test_vad_streaming.py`
- **Commit:** `801d658`

**2. [Rule 1 - Bug] Stateless noise generation in test helper**

- **Found during:** Task 1 GREEN phase (multi-test run)
- **Issue:** A first iteration used a module-level `_NOISE_RNG = np.random.default_rng(42)` that drained sequentially across tests. Test 4 (`test_silence_after_tone_produces_end_event`) failed when run after test 3 because its noise stream picked up at a position that never crossed the speech threshold — but passed in isolation. Test ordering became load-bearing.
- **Fix:** Switched to `noise_seed = int(phase * sr) & 0xFFFFFFFF` so the noise component is a deterministic function of the requested phase. Identical phases produce identical waveforms regardless of test order. The synthesizer is now fully stateless.
- **Files modified:** `backend/tests/stt/test_vad_streaming.py`
- **Commit:** `801d658`

Both deviations were Rule 1 (test bugs blocking GREEN); not architectural.

## Authentication Gates

None. This plan touches only in-process Python code with no network or auth surface.

## Commits

| Hash      | Type | Subject |
|-----------|------|---------|
| `b1633cf` | test | add failing tests for StreamingVad per-connection wrapper (RED) |
| `801d658` | feat | per-connection StreamingVad wrapper for Silero VAD (STT-02) (GREEN) |

## TDD Gate Compliance

- RED: `test(02-03)` commit `b1633cf` — 7 tests written; pytest collection failed with `ModuleNotFoundError: No module named 'receptra.stt.vad'` (correct RED state).
- GREEN: `feat(02-03)` commit `801d658` — `vad.py` created; 7/7 tests pass.
- REFACTOR: not needed (code already clean; ruff + mypy strict pass on first iteration after fixes).

## Self-Check: PASSED

- `backend/src/receptra/stt/vad.py` — exists (verified)
- `backend/tests/stt/test_vad_streaming.py` — exists (verified)
- Commit `b1633cf` (test RED) — exists (verified via `git log --oneline`)
- Commit `801d658` (feat GREEN) — exists (verified via `git log --oneline`)
- All 7 tests in test_vad_streaming.py pass (verified)
- Full backend suite 19/19 pass (verified)
- ruff + mypy strict clean (verified)
