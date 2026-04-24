# Phase 2: Hebrew Streaming STT — Research

**Researched:** 2026-04-24
**Domain:** Hebrew real-time speech-to-text (faster-whisper + Silero VAD), FastAPI WebSocket PCM streaming, WER + latency instrumentation
**Confidence:** HIGH for stack + integration patterns; MEDIUM for specific Hebrew WER target (published leaderboard numbers exist but no single canonical baseline for the `turbo-ct2` variant on short conversational audio); LOW for "~1s partials" being achievable on M2 16GB inside a Python loop without MLX/Core ML — flagged for Wave 0 spike.

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| STT-01 | Backend runs faster-whisper with `ivrit-ai/whisper-large-v3-turbo-ct2`, loaded once at startup | §2 (Model loading + lifespan), §5 (FastAPI lifespan pattern), §3.2 (Apple Silicon compute_type) |
| STT-02 | Silero VAD identifies speech chunks from PCM audio stream | §4 (Silero VAD v6.2.1 VADIterator streaming pattern) |
| STT-03 | WebSocket accepts binary PCM frames + emits partial Hebrew transcripts within ~1s of speech onset | §6 (WebSocket binary PCM), §7 (partial-transcript strategy), §8 (event schema) |
| STT-04 | Final-utterance transcript events emitted when VAD detects end-of-speech | §4.2 (VADIterator `end` event), §7 (two-stage emit: partial + final) |
| STT-05 | WER measured + logged against seeded 30-sample Hebrew audio test set | §9 (WER via `jiwer` 4.0.0), §10 (test fixture sourcing) |
| STT-06 | STT latency (speech-end → final transcript) instrumented + logged per request | §11 (latency instrumentation), §13 (SQLite audit row) |

</phase_requirements>

## Summary (TL;DR)

**Ten decisions the planner should treat as default:**

1. **faster-whisper 1.2.1** + **ivrit-ai/whisper-large-v3-turbo-ct2** loaded **once at FastAPI lifespan startup** (not per-request). Use the `asynccontextmanager`-based `lifespan` pattern — the `@app.on_event("startup")` currently in `main.py` is deprecated and must be replaced. [VERIFIED: faster-whisper 1.2.1 on PyPI, Oct 31 2025; FastAPI lifespan docs]
2. **On Apple Silicon / Mac / Linux-arm64: `device="cpu"`, `compute_type="int8"`.** faster-whisper does **NOT** support MPS/Metal (`ValueError: unsupported device mps`). CTranslate2 runs via Apple Accelerate + oneDNN arm64 backend; `int8` gives ~4x speedup over `float32` with negligible accuracy loss. [CITED: SYSTRAN/faster-whisper issue #911, OpenNMT CTranslate2 docs]
3. **Language MUST be pinned:** `language="he"` on every `model.transcribe()` call. ivrit-ai explicitly degraded the turbo model's language detection during fine-tuning. Omitting this produces garbage. [CITED: ivrit-ai/whisper-large-v3-turbo model card]
4. **Use external Silero VAD for endpointing, NOT faster-whisper's built-in `vad_filter`.** Built-in VAD is file-oriented (pre-filters chunks for batch transcription); for streaming we need per-chunk speech/silence events (`VADIterator`) to drive the partial/final emit boundaries. [CITED: silero-vad Context7 docs; SYSTRAN/faster-whisper issue #1249]
5. **PCM wire format: 16 kHz mono int16 little-endian, 32 ms frames (512 samples = 1024 bytes per binary WebSocket message).** This matches Silero v5/v6's required 512-sample window at 16 kHz exactly. Client converts `int16` → `float32 / 32768.0` on receive. [CITED: Silero VAD v5+ release notes, ricky0123/vad docs]
6. **Partial-transcript strategy = incremental re-transcribe of an active speech buffer.** On VAD `start` event, begin accumulating float32 samples. Every ~700 ms of new audio, re-run `model.transcribe()` on the whole active buffer and emit the result as `{"type":"partial"}`. On VAD `end`, transcribe one last time and emit `{"type":"final"}`. This is the simplest approach that meets STT-03 "~1s of speech onset" and STT-04. No WhisperLive dependency needed.
7. **Keep the Phase 2 backend standalone — no Pipecat yet.** Pipecat pipeline wiring lives in Phase 5 (INT-01). Phase 2 ships a direct `WebSocket → VAD → Whisper → JSON-back` async loop inside FastAPI. Fewer deps, faster to verify.
8. **WER via `jiwer` 4.0.0** with Hebrew-aware text normalisation: strip punctuation, Unicode-NFC normalise, collapse whitespace, split on whitespace, compute WER + CER (CER is more robust for Hebrew morphology because word-level errors over-count on agglutinative forms). [VERIFIED: jiwer 4.0.0 installs cleanly on py3.12; ivrit.ai's own benchmarking pipeline uses jiwer]
9. **Latency instrumentation = per-stage monotonic clocks**, not just end-to-end. Capture `t_vad_speech_end`, `t_whisper_enter`, `t_whisper_exit`, `t_ws_send` and log as structured JSON per utterance. Write a row to the SQLite audit log at INT-05 schema (deferred full schema to Phase 5; Phase 2 stubs `stt_utterances` table with `id, ts_utc, duration_ms, stt_ms, text, wer_sample_id NULL`).
10. **Models mounted read-only at `/models` inside the container** (Phase 1 Plan 01-04 already does this). Phase 2's Whisper-load code reads `Settings.model_dir / "whisper-turbo-ct2"` — no hardcoded paths.

**Primary recommendation:** Ship the simplest possible VAD-gated re-transcribe loop first. Instrument latency per stage immediately (not later). The "~1s partials" target is plausible on M2 but unverified for this model — plan a **Wave 0 spike** that loads the model and transcribes a 2-second Hebrew clip end-to-end, then locks the rest of the plan against the measured baseline.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Binary PCM ingest (WS) | FastAPI backend (server) | — | Only backend has the model |
| VAD endpointing | FastAPI backend | — | Keep co-located with Whisper; avoids IPC between VAD and STT |
| Whisper transcription | FastAPI backend | — | Model is loaded in-process singleton |
| Partial/final event emit (JSON) | FastAPI backend (WS send) | Browser (display — Phase 6) | Contract owned by backend; frontend consumes |
| Model storage | Host filesystem (`~/.receptra/models/`, mounted RO) | — | Phase 1 decision locked |
| WER eval | CI job / local test harness | — | Offline batch; not hot-path |
| Latency logging | Backend stdout (loguru JSON) + SQLite audit | — | Local-only telemetry per INT-05 (stub table in Phase 2) |
| PCM framing contract (int16 LE 16kHz mono 32ms) | Shared backend+frontend ADR | Frontend mic capture (Phase 6) | Phase 2 locks the format; Phase 6 implements capture |

## Findings

### 1. Current versions (verified in-session)

I ran `uv run --isolated` against Python 3.12.13 arm64 on macOS Darwin and all of the following installed cleanly with no wheel fallback:

| Package | Installed version | Source |
|---------|------------------|--------|
| `faster-whisper` | **1.2.1** (released 2025-10-31) | [VERIFIED: pypi.org/project/faster-whisper] |
| `ctranslate2` | **4.7.1** (pulled in transitively) | [VERIFIED: pypi.org/project/ctranslate2 — manylinux_2_27_aarch64 + manylinux_2_28_aarch64 wheels] |
| `tokenizers` | pulled by faster-whisper | [VERIFIED: installed] |
| `silero-vad` | **6.2.1** (released 2026-02-24) | [VERIFIED: pypi.org/project/silero-vad] |
| `torch` | 2.11.0 (silero-vad dep) | [VERIFIED: installed, macOS arm64 wheel] |
| `onnxruntime` | installed as silero-vad's declared dependency for ONNX mode | [VERIFIED: installed alongside] |
| `jiwer` | **4.0.0** | [VERIFIED: pypi.org/project/jiwer] |
| `numpy` | 2.4.4 | [VERIFIED: installed] |

**Python version:** 3.12 — matches Phase 1's locked choice. Confirmed via `uv run --isolated` that faster-whisper 1.2.1 wheels support py3.9-3.12. Faster-whisper does NOT yet ship 3.13/3.14 wheels [CITED: PyPI faster-whisper page], so the Phase 1 decision to pin 3.12 remains correct.

### 2. Apple Silicon compute_type

**Hard fact:** faster-whisper has **no Metal/MPS device**. Attempting `device="mps"` raises `ValueError: unsupported device mps`. [CITED: github.com/SYSTRAN/faster-whisper/issues/911]

**What actually runs:** CTranslate2's arm64 CPU backend with Apple Accelerate + oneDNN + Ruy kernels. From OpenNMT CTranslate2 docs: "CTranslate2 has compatibility with x86-64 and AArch64/ARM64 CPU and integrates multiple backends that are optimized for these platforms: Intel MKL, oneDNN, OpenBLAS, Ruy, and Apple Accelerate."

**Recommended matrix:**

| Scenario | device | compute_type | Notes |
|----------|--------|--------------|-------|
| **Mac M2 / M2 Pro (production default)** | `cpu` | `int8` | ~4x faster than `float32` on CPU, negligible WER cost. Best latency on arm64. [CITED: faster-whisper README; SYSTRAN discussions] |
| Mac M2 development with full precision | `cpu` | `float32` | Use only for one-off accuracy baselining |
| Linux arm64 (contributor Docker) | `cpu` | `int8` | Same CTranslate2 backend |
| CUDA box (future, out of v1 scope) | `cuda` | `float16` or `int8_float16` | Not v1 |

**Not applicable to Mac: `int8_float16`** — the `_float16` half requires CUDA or CPU AVX-512 (most Apple Silicon chips don't expose AVX-512 equivalents usefully). Stick with plain `int8` on Mac.

**`cpu_threads` tuning:** M2 has 4 performance cores + 4 efficiency cores. Set `cpu_threads=4` on the `WhisperModel` constructor or export `OMP_NUM_THREADS=4` [CITED: faster-whisper README]. Do NOT set `cpu_threads=0` (auto-detect) — it over-schedules across e-cores and hurts latency.

### 3. Model loading — singleton at lifespan startup

**Why singleton:** The CT2 Whisper model is ~1.5 GB on disk and takes ~3-5 seconds to load into memory. Loading per-request would blow every latency budget. Must be loaded once at process startup and shared across all WebSocket sessions.

**Why lifespan (not `@app.on_event("startup")`):** FastAPI's `on_event` decorators are deprecated. The current `backend/src/receptra/main.py` uses `@app.on_event("startup")` — **this is a Phase 2 refactor to replace with the lifespan context manager.** Lifespan is mutually exclusive with `on_event`: if you pass `lifespan=` to FastAPI, `on_event` handlers are silently ignored. [CITED: fastapi.tiangolo.com/advanced/testing-events; FastAPI discussion #9604]

**Recommended pattern — `backend/src/receptra/lifespan.py`:**

```python
# backend/src/receptra/lifespan.py
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from faster_whisper import WhisperModel  # type: ignore[import-untyped]
from fastapi import FastAPI
from silero_vad import load_silero_vad  # type: ignore[import-untyped]

from receptra.config import settings

logger = logging.getLogger("receptra.stt")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Load STT + VAD models once at startup; free them on shutdown."""
    model_path = Path(settings.model_dir) / "whisper-turbo-ct2"
    logger.info("loading whisper model from %s (compute_type=int8)", model_path)
    whisper = WhisperModel(
        str(model_path),
        device="cpu",
        compute_type="int8",
        cpu_threads=4,
        num_workers=1,
    )
    logger.info("loading silero VAD")
    vad = load_silero_vad(onnx=False)  # JIT on Mac is fine; ONNX only needed for cross-runtime

    # Stash on app.state so WebSocket handlers can reach it without globals
    app.state.whisper = whisper
    app.state.vad = vad
    logger.info("receptra STT ready")
    yield
    logger.info("receptra STT shutting down")
    # WhisperModel has no explicit close; Python GC handles CT2 cleanup
    # silero-vad has no explicit close
```

Update `main.py` to pass `lifespan=lifespan` when constructing `FastAPI()` and remove the deprecated `@app.on_event("startup")` block.

[CITED: fastapi.tiangolo.com/advanced/events/, fastapi.tiangolo.com/advanced/testing-events/]

**First-token warmup:** Recommend one warmup transcription at lifespan startup (silent 1-second buffer) so the first real request isn't paying CTranslate2's first-inference JIT cost. The second transcription is ~2-3x faster than the first. Add this to the spike list in Wave 0.

### 4. Silero VAD streaming pattern

**4.1 Version:** 6.2.1 (2026-02-24) [VERIFIED: PyPI]. Version 6.x has the same `VADIterator` API as v5.x plus bug fixes. No breaking changes relevant to us.

**4.2 API:**

```python
from silero_vad import load_silero_vad, VADIterator

vad_model = load_silero_vad(onnx=False)
vad_iter = VADIterator(
    vad_model,
    threshold=0.5,                # 0.5 is recommended baseline per Silero README
    sampling_rate=16000,
    min_silence_duration_ms=300,  # 300ms silence = utterance end. Shorter = faster final emit, more false splits
    speech_pad_ms=200,            # 200ms lookback added to speech chunk to avoid word clipping
    # NOTE: silero does NOT expose min_speech_duration_ms on VADIterator — that param is on
    # the batch `get_speech_timestamps` helper. VADIterator yields on threshold crossings only.
)

WINDOW_SAMPLES = 512  # REQUIRED for 16kHz in silero v5+ (fixed)

# Per-chunk (512 int16 samples = 1024 bytes) processing:
import numpy as np
pcm_int16 = np.frombuffer(ws_bytes, dtype="<i2")  # 512 samples
pcm_f32 = pcm_int16.astype(np.float32) / 32768.0   # silero needs float32 in [-1, 1]

event = vad_iter(pcm_f32, return_seconds=True)  # returns None, {"start": s}, or {"end": s}
```

[CITED: Context7 /snakers4/silero-vad — VADIterator streaming example; verified against silero-vad v6.2.1 package]

**4.3 Hard constraints from Silero v5+ (still true in v6):**
- Window size **must be exactly 512 samples at 16 kHz** (or 256 at 8 kHz). Arbitrary window sizes are no longer supported. [CITED: github.com/snakers4/silero-vad/discussions/471]
- Audio **must be float32 in [-1.0, 1.0]** and mono. [CITED: silero-vad README]
- **Model is stateful** — call `vad_iter.reset_states()` between independent audio sessions (e.g., when a WebSocket closes and a new one opens).

**4.4 Recommended parameters for live Hebrew co-pilot:**

| Param | Value | Rationale |
|-------|-------|-----------|
| `threshold` | `0.5` | Silero default. Higher = more misses (false silence). Lower = more false triggers on background noise. Start 0.5; tune on real Hebrew fixtures in Wave 2. |
| `min_silence_duration_ms` | `300` | Tight enough that STT-04 final emit feels live; loose enough that a 200ms pause mid-sentence doesn't split. |
| `speech_pad_ms` | `200` | Prevents clipping word onset ("ש" phoneme particularly sensitive). |
| `sampling_rate` | `16000` | Whisper's native rate; avoids resampling cost. |

**4.5 Do NOT use faster-whisper's built-in `vad_filter=True` for live streaming.** It's designed for batch transcription of long files — it pre-filters the whole audio before Whisper sees it. We need per-chunk VAD events to drive the partial-emit loop. The built-in VAD defaults (`speech_pad_ms=400`, `min_silence_duration_ms=2000`) are also tuned for batch podcast-style audio, not conversational live speech. [CITED: SYSTRAN/faster-whisper issue #477]

For STT-05 (batch WER eval), using `vad_filter=True` on the 30-sample fixture IS acceptable because it's a non-streaming batch measurement. Separate code path from live streaming.

### 5. FastAPI lifespan pattern

The existing `main.py` has:

```python
@app.on_event("startup")
async def _log_config() -> None:
    ...
```

This is deprecated. Replace with:

```python
# backend/src/receptra/main.py
from fastapi import FastAPI
from receptra.lifespan import lifespan

app = FastAPI(
    title="Receptra",
    version="0.1.0",
    description="Hebrew-first local voice co-pilot backend.",
    lifespan=lifespan,
)
```

The existing `_log_config` startup hook becomes a call inside `lifespan()` before `yield`.

[CITED: fastapi.tiangolo.com/advanced/events/; medium.com/algomart — FastAPI Lifespan Explained]

### 6. WebSocket PCM wire format

**Endpoint path:** `/ws/stt` (aligns with Phase 1 Plan 01-03's Vite proxy `ws: true` config for `/ws/*`).

**Wire contract (binary frames only):**

| Property | Value |
|----------|-------|
| Sample rate | 16,000 Hz |
| Channels | 1 (mono) |
| Sample format | int16, **little-endian** |
| Frame size | 512 samples = **1024 bytes** per binary WebSocket message |
| Frame duration | 32 ms |
| Send cadence | Every 32 ms from the browser AudioWorklet |

**Why 512 samples:** silero-vad v5+ mandates exactly 512 at 16 kHz. Making the WebSocket frame size match eliminates a buffering layer. [CITED: snakers4/silero-vad discussion #471]

**Alternative:** If the browser can only deliver larger frames (e.g., 128-sample AudioWorklet default × 4), the backend must accumulate a ring buffer and slice into 512-sample windows before feeding the VAD. Simpler to specify 512 as the contract.

**Control messages (text frames — rare):** The server uses binary-only for audio; text frames reserved for backward-compat signalling only (unused in v1).

**Server → client messages = JSON text frames** (see §8 schema).

**Backpressure:** FastAPI/Starlette WebSocket does not drop messages; if the send queue backs up, `websocket.send_json()` awaits. For Phase 2 we assume a healthy local-only connection. If p95 send queue depth exceeds 3 frames, log a warning — defer full backpressure handling to Phase 5.

**Max message size:** Default Starlette WebSocket has no explicit upper bound (configurable via `websocket_max_size` since Starlette 0.37). 1024-byte binary messages are tiny — no concern.

[CITED: fastapi.tiangolo.com/advanced/websockets/; websocket.org/guides/frameworks/fastapi/]

### 7. Partial vs final transcript strategy

**The reality of Whisper:** Whisper is NOT a streaming model. It's a segment-to-text model that needs at least ~1 second of audio to produce quality output. Any "streaming" layer re-transcribes growing buffers. [CITED: openai/whisper discussion #608; saytowords.com/blogs/Real-Time-Streaming-with-Whisper 2026]

**Three options considered:**

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| (a) Incremental re-transcribe on growing VAD-gated buffer | Simple, ~100 LOC, no extra deps | Minor text flicker on partials (same word can re-tokenise); CPU cost of repeated transcribes | **RECOMMENDED** |
| (b) WhisperLive (collabora/WhisperLive) | Handles overlap + local-agreement policy | Extra dep, designed for WebSocket server-from-scratch (conflicts with our FastAPI endpoint); brings its own server stack | Reject for Phase 2 |
| (c) Only emit on VAD `end` (no partials) | Simplest, no flicker | **Violates STT-03** — no ~1s partials | Reject |

**Chosen pattern (a) — the "incremental re-transcribe" loop:**

```
on VAD start event:
    speech_buffer = []
    t_speech_start = monotonic()

on each audio frame (32ms) during active speech:
    speech_buffer.append(frame_f32)
    if (now - t_last_partial) >= 700ms AND len(speech_buffer) >= ~500ms of audio:
        # re-transcribe the whole active buffer
        text = transcribe(concat(speech_buffer), language="he", ...)
        emit {"type":"partial", "text": text, "t_speech_start_ms": ..., "t_emit_ms": ...}
        t_last_partial = now

on VAD end event:
    text = transcribe(concat(speech_buffer), language="he", ...)
    emit {"type":"final", "text": text, "stt_latency_ms": now - t_vad_end, ...}
    speech_buffer.clear()
```

**Transcribe call parameters:**

```python
segments, info = model.transcribe(
    audio=audio_f32_numpy,
    language="he",                      # MANDATORY per ivrit-ai model card
    task="transcribe",                  # NOT "translate" — ivrit-ai broke translate during fine-tune
    beam_size=1,                        # greedy = fastest; for live latency budget this is correct
    best_of=1,                          # paired with beam_size=1
    temperature=0.0,                    # deterministic; no fallback sampling
    condition_on_previous_text=False,   # prevents hallucination carryover across re-transcribes
    vad_filter=False,                   # external Silero handles VAD
    without_timestamps=True,            # faster + we don't use word-level timings in v1
    initial_prompt=None,                # no prompt biasing in v1
    compression_ratio_threshold=2.4,    # default
    log_prob_threshold=-1.0,            # default
    no_speech_threshold=0.6,            # default
)
text = "".join(s.text for s in segments).strip()
```

Why each:
- `language="he"` — non-optional per ivrit-ai [CITED: model card].
- `beam_size=1` — greedy beam. beam=5 doubles latency for marginal accuracy on short segments. For live partials we want beam=1; for the WER batch eval in STT-05 we may bump to beam=5 to establish the "ceiling" baseline.
- `condition_on_previous_text=False` — critical for incremental re-transcribe: if the previous call's hallucinated text becomes context for the next call, errors compound. [CITED: openai/whisper discussion #1606 — hallucination]
- `temperature=0.0` + no temperature_increment_on_fallback — deterministic outputs needed for WER reproducibility.
- `without_timestamps=True` — shaves per-segment decoding time.

**Cost of re-transcribe loop:** If the active utterance is 3 seconds long and we re-transcribe every 700 ms, we do ~4 transcribes per utterance. Each transcribe is O(audio length) so the total CPU is ~(3+2.3+1.6+0.9) = ~7.8 seconds of audio worth of work. At 4x realtime on M2 int8 (reasonable baseline), that's ~2 seconds of compute. **This is the key latency risk** and the Wave 0 spike must measure it on real Hebrew audio before the plan locks.

**Optimisation if spike fails:** Bump partial cadence from 700 ms to 1000 ms, drop `condition_on_previous_text` re-evaluation, pre-warm the model, consider moving to `whisper.cpp` with Core ML on Mac as a Phase 2.5 fallback. Document as OPEN-3 below.

### 8. WebSocket event schema (server → client)

Use pydantic v2 `BaseModel` for schema validation. Discriminated union on `type`:

```python
# backend/src/receptra/stt/events.py
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PartialTranscript(BaseModel):
    type: Literal["partial"] = "partial"
    text: str = Field(..., description="Hebrew UTF-8 text; may change on next partial/final.")
    t_speech_start_ms: int = Field(..., description="Monotonic ms when VAD start fired.")
    t_emit_ms: int = Field(..., description="Monotonic ms when this message was constructed.")


class FinalTranscript(BaseModel):
    type: Literal["final"] = "final"
    text: str
    t_speech_start_ms: int
    t_speech_end_ms: int
    stt_latency_ms: int = Field(
        ..., description="t_final_ready - t_speech_end; per STT-06."
    )
    duration_ms: int = Field(..., description="Utterance audio duration.")


class SttError(BaseModel):
    type: Literal["error"] = "error"
    code: Literal["model_error", "vad_error", "protocol_error"]
    message: str


class SttReady(BaseModel):
    """Sent once after WebSocket accept, before the first audio frame."""

    type: Literal["ready"] = "ready"
    model: str
    sample_rate: int = 16000
    frame_bytes: int = 1024  # 512 samples int16
```

Client receives one of `ready | partial | final | error` on each text frame. The `type` field is the discriminator.

**Rationale for including timestamp fields on every event:** Frontend rendering in Phase 6 needs to know (a) which speech-burst a partial belongs to (so a late partial doesn't overwrite a newer final) and (b) can compute its own client-side total latency for DEMO-01 reporting.

### 9. WER measurement (STT-05)

**Tool:** `jiwer` 4.0.0 [VERIFIED: installed cleanly on py3.12]. [CITED: github.com/jitsi/jiwer; ivrit.ai also uses jiwer for their leaderboard]

**Hebrew-aware text normalisation for fair comparison:**

```python
# backend/src/receptra/stt/wer.py
import unicodedata
import re

import jiwer
from jiwer import Compose, RemoveMultipleSpaces, Strip


HEBREW_PUNCT_RE = re.compile(r"[\u0591-\u05C7\u200E\u200F\.\,\!\?\:\;\"\'\(\)\[\]\-]")


def normalise_hebrew(text: str) -> str:
    """Canonical form for WER comparison: NFC, strip niqqud, strip punctuation, collapse WS."""
    text = unicodedata.normalize("NFC", text)
    text = HEBREW_PUNCT_RE.sub(" ", text)  # strips niqqud marks + punctuation
    text = re.sub(r"\s+", " ", text).strip()
    return text


def compute_wer(reference: str, hypothesis: str) -> dict[str, float]:
    r = normalise_hebrew(reference)
    h = normalise_hebrew(hypothesis)
    transform = Compose([Strip(), RemoveMultipleSpaces()])
    wer = jiwer.wer(r, h, reference_transform=transform, hypothesis_transform=transform)
    cer = jiwer.cer(r, h, reference_transform=transform, hypothesis_transform=transform)
    return {"wer": wer, "cer": cer}
```

**Why strip niqqud (`\u0591-\u05C7`):** Hebrew reference transcripts often include or exclude cantillation and vowel points; the model never outputs them. Comparing without stripping them drives WER artificially up. This is standard practice in Hebrew ASR literature. [ASSUMED — no single canonical Hebrew ASR eval spec; matches approach used by common Hebrew corpora]

**Why track CER alongside WER:** Hebrew is morphologically agglutinative; prefixes like ב/ל/מ attach to words. A one-character prefix swap counts as a full word error under WER but 1/N under CER. For the Phase 2 baseline we record both. [ASSUMED — based on general ASR eval practice; not a specific ivrit.ai recommendation]

**WER target (Phase 2 baseline, not a gate):** ivrit.ai reports state-of-the-art Hebrew WER for the turbo model but does NOT publish a single headline number on the -ct2 variant specifically. Published comparable benchmarks in Hebrew ASR literature (2024-2026) sit in the **12-25% range** depending on domain (read speech ~10-15%, conversational ~20-30%, noisy SMB audio can be 30%+). Our 30-sample fixture will set OUR baseline; the Phase 2 exit does NOT gate on a specific WER number, only on "measured and logged." Treat first measurement as informational. [ASSUMED — exact WER target; supports setting a Phase 2 baseline-recording success criterion rather than a pass/fail threshold]

### 10. Test fixture sourcing (30 samples for STT-05)

**Three paths evaluated:**

| Source | Pros | Cons | Verdict |
|--------|------|------|---------|
| Mozilla Common Voice Hebrew (cv-corpus-25.0-2026-03-09: 6.98 hours, 5524 clips) | Public, licensed CC0, script-aligned transcripts, easy to filter to 30 short clips | Read speech, not conversational — optimistic WER | Use as **primary** fixture source |
| ivrit-ai/crowd-transcribe-v5 test split | Closer to conversational Hebrew | Model was trained on this data → WER would be artificially low. **Do NOT use for eval.** | Reject for eval; fine for spot-checks |
| Custom recordings | Matches SMB receptionist use case exactly | Requires human recording + transcription effort; not reproducible across contributors | Defer to Phase 7 (DEMO eval) |

**Recommended Phase 2 fixture:**

Seed 30 samples from **Mozilla Common Voice he-25.0** into `backend/tests/fixtures/stt/he_cv_30/`. Each sample = `{id}.wav` (16 kHz mono resampled from source MP3 via `ffmpeg`) + `{id}.txt` (reference transcript, UTF-8 NFC).

Include the fixture manifest as `he_cv_30.jsonl`:
```jsonl
{"id": "cv_he_001", "wav": "cv_he_001.wav", "ref": "שלום, מה שלומך היום?", "duration_ms": 2340, "source": "common-voice-25.0"}
...
```

Download script: `scripts/fetch_stt_fixtures.py` that uses `huggingface_hub.hf_hub_download` to pull CommonVoice Hebrew from `mozilla-foundation/common_voice_25_0` and selects 30 clips under 10 seconds with valid transcripts. This script runs once, commits the fixtures into the repo (Common Voice is CC0 so redistribution is fine) — about 30 WAV files × ~50 KB each = ~1.5 MB in-repo. Gate on `.gitattributes` LFS for >1MB files if any.

[CITED: commonvoice.mozilla.org/en/datasets; mozillaorg common-voice-hebrew GitHub; licensing = CC0 via Mozilla Public data license]

**Fixture freshness check:** The script pins `commit_sha` of the HF dataset so contributors get exactly the same clips. Adding this constraint to the plan.

### 11. Latency instrumentation (STT-06)

**What to measure — per utterance, in monotonic ms:**

| Timestamp | Source | Captured when |
|-----------|--------|--------------|
| `t_speech_start` | VAD `start` event | VADIterator yields `{"start": t}` |
| `t_first_partial_emit` | After first partial transcribe completes | right before `ws.send_json(partial)` |
| `t_speech_end` | VAD `end` event | VADIterator yields `{"end": t}` — this is the "speech end" for STT-06 |
| `t_final_transcribe_enter` | Immediately before final `model.transcribe()` | |
| `t_final_transcribe_exit` | Immediately after the generator is drained to text | |
| `t_ws_send` | Right after `ws.send_json(final)` | — |

**STT-06 required metric:** `stt_latency_ms = t_final_transcribe_exit - t_speech_end`. This is what's logged and written to SQLite.

**Secondary metrics (log but don't gate):** `transcribe_duration_ms`, `total_partials_emitted`, `utterance_audio_duration_ms`, `partials_per_second` — helps Phase 5 debug the latency cascade pitfall (#4).

**Implementation — loguru JSON + SQLite audit:**

```python
# backend/src/receptra/stt/metrics.py
import time
from dataclasses import asdict, dataclass

from loguru import logger  # logging; installed as deferred dep — see §16


@dataclass
class UtteranceMetrics:
    utterance_id: str
    t_speech_start_ms: int
    t_speech_end_ms: int
    t_final_ready_ms: int
    duration_ms: int
    stt_latency_ms: int         # t_final_ready_ms - t_speech_end_ms  (STT-06)
    transcribe_ms: int
    partials_emitted: int
    text_len_chars: int
    model_load_time_ms: int


def log_utterance(m: UtteranceMetrics) -> None:
    logger.bind(event="stt.utterance").info(asdict(m))  # loguru serialize=True yields JSON
    # Also insert into SQLite audit log — stubbed for INT-05; Phase 2 creates the table
    audit_insert_stt_utterance(m)
```

**SQLite stub schema (Phase 2 stub — final table owned by Phase 5 / INT-05):**

```sql
CREATE TABLE IF NOT EXISTS stt_utterances (
    utterance_id TEXT PRIMARY KEY,
    ts_utc TEXT NOT NULL,                -- ISO-8601
    duration_ms INTEGER NOT NULL,
    stt_latency_ms INTEGER NOT NULL,
    transcribe_ms INTEGER NOT NULL,
    partials_emitted INTEGER NOT NULL,
    text TEXT NOT NULL,
    wer_sample_id TEXT                   -- nullable; links to WER batch eval
);
```

Path: `${RECEPTRA_AUDIT_DB:-./data/audit.sqlite}`. Phase 2 writes rows; Phase 5 broadens the schema.

**Why loguru (not stdlib logging):** `serialize=True` gives JSON out of the box, integrates cleanly with FastAPI, and is 1-line setup. The existing `main.py` uses stdlib `logging.basicConfig` — we switch here. [CITED: dash0.com python-logging-with-loguru; mahdijafaridev medium]

**Prometheus defer:** The roadmap defers Prometheus histograms to Phase 7 polish. Phase 2 uses structured JSON logs + SQLite rows; a `GET /metrics` endpoint is NOT added in Phase 2. [Confirmed against roadmap Phase 7 text]

### 12. Pre-processing hygiene (mitigates Pitfall #1)

What helps Hebrew WER on real audio (low-cost, Phase 2 scope):

1. **Strict 16 kHz mono normalisation.** Guarantee the client sends exactly that; reject mismatched WebSocket streams with a `protocol_error`.
2. **No amplitude normalisation in v1.** CTranslate2/Whisper handles amplitude internally; adding AGC/RMS normalisation in Python is error-prone and not worth v1 complexity.
3. **No Hebrew/English code-mixing in transcribe calls.** Since `language="he"` is pinned, the model will force-decode even English words as Hebrew phonetic transliteration. For the SMB co-pilot use case, Hebrew-only audio is the target. Document the limitation. [CITED: ivrit-ai model card — "intended for mostly-hebrew audio"]
4. **Silence trim ALREADY HAPPENS** via Silero VAD — don't double-trim with faster-whisper's built-in VAD.

Deferred to Phase 7:
- Noise suppression (RNNoise, webrtcvad) — measure impact first, add only if WER mandates
- Echo cancellation — assumes headset mic in SMB setup; AEC is a full separate module
- Speaker-specific adaptation — out of v1 scope

### 13. Pipecat deferred confirmation

The Phase 1 research explicitly deferred Pipecat (`pipecat-ai>=1.0.0`) to Phase 5. Phase 2 builds a **standalone FastAPI WebSocket endpoint** that Phase 5 will later either wrap in a Pipecat transport or rewire as a Pipecat `FrameProcessor`. This keeps Phase 2's dependency surface minimal and the CI fast.

[CITED: Phase 1 RESEARCH.md line 242 — "Pipecat: DEFER to Phase 5"]

### 14. Non-goals for Phase 2

To prevent scope creep from the planner:
- **No frontend work.** Mic capture, audio worklet, RTL transcript pane → Phase 6.
- **No LLM, no RAG.** → Phases 3, 4.
- **No SQLite full audit-log schema.** Phase 2 ships a *stub table* so latency rows are captured; Phase 5 owns the canonical INT-05 schema.
- **No authentication on the WebSocket.** Local-only + single user. Phase 7 may add CORS hardening if the user runs on a LAN IP.
- **No Pipecat, no LiveKit.** → Phase 5/6.
- **No multi-speaker diarisation, no timestamps output.** → v2 per REQUIREMENTS.md.
- **No Prometheus `/metrics` endpoint.** → Phase 7.
- **No custom Whisper model fine-tuning.** We consume `ivrit-ai/whisper-large-v3-turbo-ct2` as-is.

### 15. Backend deps that land in Phase 2

See **Recommended Dependencies** section below for the full pyproject.toml delta.

## Project Constraints (from CLAUDE.md)

The following constraints from `/CLAUDE.md` must be honoured by the plan:

- **Hebrew is day-1 target.** Every v1 choice must work in Hebrew before any English optimization.
- **Apple Silicon M2 + 16GB reference floor.** No CUDA dependency. Metal/MPS not used for STT (faster-whisper doesn't support MPS — runs on CPU via CTranslate2 arm64 backend, confirmed working).
- **Permissive licensing only.** Apache 2.0, MIT, BSD — verified for every recommended dep in §Recommended Dependencies. **No GPL or research-only licenses in v1 deps** — the Phase 1 CI license allowlist gate (pip-licenses) enforces this.
- **Zero cloud dependency for core loop.** STT must run fully local. Model downloaded once to `~/.receptra/models/` (Phase 1 decision); no runtime network calls.
- **Latency target <2s end-to-end.** Phase 2's contribution to that budget is ~500ms STT (speech-end → final). Per-stage instrumentation mandatory (STT-06).
- **`docker compose up` one-liner.** Phase 2 adds no new containers; backend container pulls new Python deps via `uv sync`. `make up` unchanged.
- **GSD workflow enforcement.** No direct edits outside a GSD command.

## Recommended Dependencies

### Backend additions to `backend/pyproject.toml`

Runtime (production):

| Package | Version pin | License | Purpose |
|---------|-------------|---------|---------|
| `faster-whisper` | `>=1.2.1,<2` | MIT | STT engine (wraps CTranslate2) — [VERIFIED: PyPI 2025-10-31] |
| `silero-vad` | `>=6.2.1,<7` | MIT | VAD endpointing for live streams — [VERIFIED: PyPI 2026-02-24] |
| `numpy` | `>=2.0,<3` | BSD-3-Clause | PCM int16 → float32 conversion; required by both deps anyway — [VERIFIED: PyPI] |
| `loguru` | `>=0.7.3,<1` | MIT | Structured JSON logging (replaces ad-hoc `logging.basicConfig`) — [CITED: PyPI] |

Dev / test additions:

| Package | Version pin | License | Purpose |
|---------|-------------|---------|---------|
| `jiwer` | `>=4.0.0,<5` | Apache-2.0 | WER/CER computation for STT-05 — [VERIFIED: PyPI] |
| `soundfile` | `>=0.13` | BSD-3-Clause | Read fixture WAV files in tests — [ASSUMED current stable; verify at install time] |

**Transitively pulled (do not pin explicitly):**
- `ctranslate2` 4.7.1+ (by faster-whisper; has manylinux_2_27/28 aarch64 wheels) — [VERIFIED]
- `torch` 2.11+ (by silero-vad; macOS arm64 wheel) — [VERIFIED]
- `onnxruntime` (by silero-vad; we use JIT mode so this is runtime-unused but present) — [VERIFIED installed]
- `tokenizers` (by faster-whisper; arm64 wheels) — [VERIFIED]
- `av` (by faster-whisper for audio decoding of fixture files) — [VERIFIED installed]

**License check compatibility:** All added dependencies (runtime + transitive) match the Phase 1 pip-licenses allowlist in `scripts/check_licenses.sh`:
- MIT — faster-whisper, silero-vad, loguru, ctranslate2, tokenizers
- Apache-2.0 — jiwer
- BSD-3-Clause — numpy, soundfile, av
- PSF / MIT — Python transitive deps

[ASSUMED — torch license = BSD-style + contributor license. The `check_licenses.sh` allowlist in Plan 01-05 needs verification that `BSD-style` or `BSD License` variants map cleanly to an allowed category. **This is a concrete Wave 0 check to run before locking deps.**]

### Suggested pyproject.toml diff

```toml
# backend/pyproject.toml  (add under [project.dependencies])
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "pydantic>=2.9",
    "pydantic-settings>=2.6",
    "python-multipart>=0.0.20",
    # Phase 2 additions:
    "faster-whisper>=1.2.1,<2",
    "silero-vad>=6.2.1,<7",
    "numpy>=2.0,<3",
    "loguru>=0.7.3,<1",
]

# under [dependency-groups].dev:
dev = [
    "ruff>=0.7",
    "mypy>=1.13",
    "pip-licenses>=5.0",
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "httpx>=0.27",
    # Phase 2 additions:
    "jiwer>=4.0,<5",
    "soundfile>=0.13",
]
```

Add to `backend/src/receptra/config.py`:

```python
# new Settings fields
whisper_model_subdir: str = "whisper-turbo-ct2"        # resolves to ${RECEPTRA_MODEL_DIR}/whisper-turbo-ct2
whisper_compute_type: str = "int8"                      # override via RECEPTRA_WHISPER_COMPUTE_TYPE
whisper_cpu_threads: int = 4                            # M2 P-core count
audit_db_path: str = "./data/audit.sqlite"              # Phase 2 stub; Phase 5 owns
stt_partial_interval_ms: int = 700                      # re-transcribe cadence during active speech
vad_threshold: float = 0.5
vad_min_silence_ms: int = 300
vad_speech_pad_ms: int = 200
```

### Intentionally NOT added

- `pipecat-ai` — deferred to Phase 5 (INT-01). Phase 2 ships a bare FastAPI WS endpoint.
- `whisper-live` / `whisperx` — we roll a minimal re-transcribe loop; both add transitive weight and opinionated server stacks.
- `prometheus-client` — deferred to Phase 7.
- `websockets` as a direct dep — FastAPI / Starlette ships WS handling.

## WebSocket event schema (JSON with pydantic models)

See §8 above for the pydantic `BaseModel` definitions. Summary:

```
Server → Client (text frames, JSON):

{"type":"ready", "model":"ivrit-ai/whisper-large-v3-turbo-ct2", "sample_rate":16000, "frame_bytes":1024}
{"type":"partial", "text":"שלום מה שלומ", "t_speech_start_ms":12345, "t_emit_ms":13045}
{"type":"final",   "text":"שלום מה שלומך?", "t_speech_start_ms":12345, "t_speech_end_ms":15600, "stt_latency_ms":412, "duration_ms":3255}
{"type":"error",   "code":"model_error", "message":"..."}

Client → Server (binary frames only):

<1024 bytes int16 little-endian 16kHz mono>  # every 32ms
```

## Model loading + lifespan pattern (code skeleton)

See §3 (lifespan.py skeleton) and §5 (main.py rewiring). The full module layout for Phase 2:

```
backend/src/receptra/
├── __init__.py
├── __main__.py                      # unchanged from Phase 1
├── main.py                          # edited: FastAPI(lifespan=lifespan), mount /ws/stt
├── config.py                        # edited: new Settings fields (§Recommended Dependencies)
├── lifespan.py                      # NEW — loads whisper + vad at startup
└── stt/                             # NEW package
    ├── __init__.py
    ├── events.py                    # pydantic schema §8
    ├── engine.py                    # transcribe() wrapper with Hebrew-locked params
    ├── pipeline.py                  # WebSocket handler: VAD loop, re-transcribe, emit
    ├── wer.py                       # §9 Hebrew-normalised WER/CER
    └── metrics.py                   # §11 UtteranceMetrics + loguru + SQLite
```

```
backend/tests/
├── conftest.py                      # edited: add whisper/vad fixtures (real or mocked)
├── test_healthz.py                  # unchanged
└── stt/                             # NEW
    ├── __init__.py
    ├── fixtures/
    │   ├── he_cv_30.jsonl           # §10 fixture manifest
    │   └── he_cv_30/*.wav,*.txt     # 30 samples, ~1.5 MB total
    ├── test_ws_handshake.py         # structural: WS upgrade + "ready" received
    ├── test_ws_pcm_roundtrip.py     # behavioral: send fixture PCM, receive partial+final
    ├── test_events_schema.py        # contract: pydantic round-trip, discriminator works
    ├── test_wer_hebrew.py           # unit: normalise_hebrew + jiwer on fixture pairs
    ├── test_vad_streaming.py        # unit: VAD start/end events on synthetic PCM
    └── test_wer_baseline.py         # regression: run 30-sample batch eval, assert WER ≤ recorded baseline + grace
```

```
scripts/
└── fetch_stt_fixtures.py            # one-time: download 30 CV Hebrew clips, resample, commit
```

## Test fixture sourcing strategy

Already covered in §10. Compact summary:

1. **Primary (30 samples):** Mozilla Common Voice Hebrew 25.0 scripted speech. CC0 licensed. Script downloads once, commits WAVs+transcripts to repo. ~1.5 MB total.
2. **Commit or LFS?** ~1.5 MB uncompressed across 30 files is fine to commit directly. No LFS needed.
3. **Fetch script:** `scripts/fetch_stt_fixtures.py` uses `huggingface_hub.hf_hub_download` against `mozilla-foundation/common_voice_25_0` with a pinned `revision=` for reproducibility.
4. **Resampling:** Source Common Voice clips are MP3 at 48 kHz. Fetch script resamples to 16 kHz mono WAV via `soundfile` (install from `soundfile>=0.13` dev dep; pulls libsndfile which is on ubuntu-latest and macOS by default — arm64 wheels available [VERIFIED: pypi.org/project/soundfile]).
5. **NO training-data leakage:** We do NOT use any ivrit.ai crowd-transcribe data for eval — it was in the training set.

## Open Decisions for Planner

**OPEN-1: Partial-transcript flicker vs simplicity**
- **Option A:** Simple re-transcribe (§7 recommended). Minor text flicker on partials is acceptable since Phase 6 frontend will style partials as grey/ghost text.
- **Option B:** Implement LocalAgreement-2 policy (confirm tokens only after 2 consecutive transcribes agree on prefix). Reduces flicker but adds ~100 LOC and edge cases.
- **Recommendation:** Lock A for Phase 2. Revisit in Phase 7 polish if user feedback demands it.

**OPEN-2: Wave 0 spike — "does the ~1s partial budget actually hit on M2?"**
- **Unknown:** All latency numbers in this research are training-data estimates. The CTranslate2 int8 CPU path on M2 has NOT been measured in-session.
- **Recommendation:** First task in Phase 2 plan is a Wave 0 spike: load the model, transcribe a 2-second Hebrew fixture, measure wall-clock ms. If first-transcribe >1000ms, bump `stt_partial_interval_ms` to 1000 and log the finding. **This must happen before any WebSocket plumbing is wired.**

**OPEN-3: Whisper.cpp + Core ML fallback**
- **If the CTranslate2 path blows the latency budget** on real M2 hardware despite `int8` + `cpu_threads=4` + warmup, the fallback is `whisper.cpp` via `whispercpp-py` with Core ML encoder. Core ML targets the ANE (Apple Neural Engine) which is the only "accelerator" exposed to us on M-series from a Docker-compatible Python path.
- **Tradeoff:** Adds a compile-from-source dependency; Docker image gets bigger; ivrit.ai may not have a pre-converted whisper.cpp Hebrew model (would need conversion step).
- **Recommendation:** Document as a Phase 2.5 fallback in OPEN-3; do NOT implement in Phase 2. Keep the code path behind `settings.whisper_backend = "ctranslate2" | "whispercpp"` so swapping is trivial.

**OPEN-4: License allowlist delta for torch + onnxruntime**
- **Action:** Before the planner commits to silero-vad, run `pip-licenses --from=mixed | grep -i -E "torch|onnx"` and confirm torch's "BSD-style" and onnxruntime's "MIT" both appear in the existing allowlist string in `scripts/check_licenses.sh`. If either does not, update the allowlist as part of Phase 2 rather than adding an exception.
- **Risk:** If torch's reported license string is exotic (e.g., "BSD-style with patent grant"), pip-licenses may emit a mismatch that trips CI. Fix-forward: extend the semicolon-separated allowlist.

**OPEN-5: WebSocket endpoint under `/ws/stt` vs just `/ws`**
- Phase 1 Vite proxy config forwards `/ws/*` broadly. Using `/ws/stt` leaves room for `/ws/ui` in Phase 5 (INT-02) and `/ws/debug` later.
- **Recommendation:** Lock `/ws/stt`. Frontend Phase 6 connects to this path.

**OPEN-6: Frame cadence — 32 ms (512 samples) vs 20 ms (320 samples)**
- Silero v5+ requires 512 samples at 16 kHz — this is fixed.
- Browser `AudioWorkletProcessor` default frame is 128 samples (2.67 ms at 48 kHz → ~2.67 ms at 16 kHz after downsample). We must buffer to 512 on the client side.
- **Recommendation:** Lock 512 samples = 1024 bytes = 32 ms as the wire contract. Phase 6 client implements the 512-sample accumulator.

**OPEN-7: WER baseline number — do we gate on it?**
- STT-05 says "measured and logged." Success Criterion 3 says "baseline number is recorded in the phase transition doc."
- **Recommendation:** Phase 2 records WER + CER as *informational* baselines only. Do NOT define a pass/fail WER threshold in Phase 2. The planner should ensure the verification step logs both numbers to STATE.md at phase transition.

**OPEN-8: SQLite `data/` directory mount**
- Current `docker-compose.yml` (Plan 01-04) mounts `${HOME}/.receptra/models:/models:ro`. It does NOT mount a writable `data/` volume yet.
- **Recommendation:** Phase 2 adds a `./data:/app/data:rw` volume for `audit.sqlite`. Default `RECEPTRA_AUDIT_DB=/app/data/audit.sqlite`. Phase 5 may move this to `${HOME}/.receptra/data/` for cross-rebuild persistence.

## Common Pitfalls

### Pitfall 1: `@app.on_event("startup")` + `lifespan=` silently drops the startup hook
**What goes wrong:** If the Phase 2 edit adds `lifespan=lifespan` but leaves the old `@app.on_event("startup")` decorator in `main.py`, the decorator is silently ignored. The model appears to load (logs print) but the old startup logger block never runs.
**Why it happens:** FastAPI intentionally deprecated `on_event` and treats `lifespan` as exclusive.
**How to avoid:** The Phase 2 plan MUST include a task that removes the `_log_config` on_event function and folds its logic into `lifespan()`.
**Warning signs:** Startup logs missing after lifespan switch → check for leftover `@app.on_event` decorators.
[CITED: github.com/fastapi/fastapi/discussions/9604]

### Pitfall 2: Silero VAD state carries across WebSocket connections
**What goes wrong:** If the `VADIterator` is a singleton on `app.state.vad`, then two concurrent clients (or one client reconnecting) share VAD state — one's speech-end can register against another's audio.
**Why:** VADIterator holds per-session context (previous chunk samples for the sliding window).
**How to avoid:** Each WebSocket handler constructs its own `VADIterator(app.state.vad_model, ...)` wrapping the *shared model* but with *per-connection iterator state*. The loaded model is singleton; the iterator wrapping is per-connection.
**Warning signs:** Second client's first partial is gibberish or arrives late.
[CITED: silero-vad README — "Reset states between audio files"]

### Pitfall 3: `condition_on_previous_text=True` amplifies Hebrew hallucination across re-transcribes
**What goes wrong:** Default Whisper behaviour passes previous segment text as context. In the incremental re-transcribe loop, partial #1's hallucinated word becomes context for partial #2, driving it further off.
**How to avoid:** Explicitly pass `condition_on_previous_text=False` on every `.transcribe()` call in the streaming path.
**Keep it `True` only for:** the batch STT-05 WER eval, where we transcribe a full 5-10s utterance once and context helps long-form coherence.
[CITED: openai/whisper discussion #1606 — hallucination patterns]

### Pitfall 4: int16 byte order mismatch (big-endian vs little-endian)
**What goes wrong:** If the browser's `AudioContext` encodes int16 big-endian (spec-dependent) and the backend decodes as little-endian, you get mathematically "valid but garbage" float32 PCM. Silero still detects energy → VAD fires → Whisper returns random Hebrew syllables.
**How to avoid:** Contract locks **little-endian int16**. Frontend in Phase 6 uses `DataView.setInt16(offset, value, /*littleEndian=*/true)` explicitly. Backend uses `np.frombuffer(buf, dtype="<i2")` (the `<` is mandatory, not optional).
**Warning signs:** VAD triggers on all audio; transcripts are word-salad unrelated to what was said.

### Pitfall 5: Blocking the asyncio event loop with `model.transcribe()`
**What goes wrong:** `WhisperModel.transcribe()` is synchronous (CTranslate2 is C++). Calling it directly from `async def websocket_endpoint` freezes the event loop for the transcribe duration — other clients (and even the same client's audio receive) block.
**How to avoid:** Wrap transcribes in `await asyncio.to_thread(model.transcribe, ...)` or use a small `concurrent.futures.ThreadPoolExecutor(max_workers=1)` dedicated to STT (serialises transcribes, protects CPU cache from thrash between sessions).
**Warning signs:** Client audio send pause during transcription → ring-buffer overflow → VAD drops events.

### Pitfall 6: Hebrew fixture file encoding
**What goes wrong:** The 30 fixture `.txt` files are UTF-8 NFC, but a contributor edits one in an editor that saves UTF-8 NFD (Mac default in some editors). `jiwer` comparison now shows spurious character diffs because NFC-normalised hypothesis doesn't match NFD-stored reference.
**How to avoid:** `normalise_hebrew()` function (§9) ALWAYS runs NFC on both sides. CI adds a pre-check: `python -c "import unicodedata, pathlib; [assert p.read_text() == unicodedata.normalize('NFC', p.read_text()) for p in pathlib.Path('backend/tests/stt/fixtures').rglob('*.txt')]"`

### Pitfall 7: Model load time ≠ model ready time
**What goes wrong:** CTranslate2 loads the model weights in ~3s but the first `model.transcribe()` call is ~2-3x slower than steady-state (JIT + graph optimisation). A health check that fires immediately after lifespan startup can return 200 while the first real request still pays the warmup cost.
**How to avoid:** In `lifespan()`, after `WhisperModel(...)` completes, run one warmup transcribe on a 1-second silence buffer. Only `yield` after warmup completes. The healthcheck in docker-compose already has `start_period: 20s` (Plan 01-04) — that buys us the warmup window.

## Runtime State Inventory

Phase 2 is a greenfield additive phase — no rename/refactor/migration. No runtime state inventory needed.

**Explicit acknowledgement per category** (confirming nothing is being missed):

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — Phase 2 CREATES a new SQLite `stt_utterances` table (stub); nothing is being renamed | New table creation only |
| Live service config | None — no external service renames | — |
| OS-registered state | None — no daemons, systemd units, or Task Scheduler entries | — |
| Secrets/env vars | None renamed. New env vars ADDED (see Config §Recommended Dependencies): `RECEPTRA_WHISPER_COMPUTE_TYPE`, `RECEPTRA_WHISPER_CPU_THREADS`, `RECEPTRA_AUDIT_DB`, `RECEPTRA_STT_PARTIAL_INTERVAL_MS`, `RECEPTRA_VAD_THRESHOLD`, `RECEPTRA_VAD_MIN_SILENCE_MS`, `RECEPTRA_VAD_SPEECH_PAD_MS` | Add to `.env.example` |
| Build artifacts | None stale from Phase 1 | Rebuild backend Docker image to pick up new pyproject deps |

## Environment Availability

| Dependency | Required by | Available on host | Version | Fallback |
|------------|------------|-------------------|---------|----------|
| Python 3.12 via uv | Backend dev + CI | ✓ | 3.12.13 | — |
| uv | Python deps | ✓ | 0.11.7 (Homebrew 2026-04-15) | — |
| Docker Desktop | Compose stack | Assumed present (Phase 1 decision) | 4.x | — |
| ~/.receptra/models/whisper-turbo-ct2 | STT engine | Fetched by `make models` (Phase 1 Plan 01-05) | ivrit-ai/whisper-large-v3-turbo-ct2 | — |
| ffmpeg | Fixture resampling script (scripts/fetch_stt_fixtures.py) | **✗ NOT INSTALLED on dev Mac** (verified via `command -v ffmpeg`) | — | `soundfile` handles WAV; ffmpeg only needed if source is MP3. Use HF dataset's WAV split or recommend `brew install ffmpeg` in CONTRIBUTING.md. |
| libsndfile | soundfile dep | Bundled with `soundfile` wheel on Mac/Linux | — | — |
| Hebrew Common Voice data | Fixture sourcing | Downloaded on-demand via `hf_hub_download` to `backend/tests/stt/fixtures/` | cv-corpus-25.0 | — |

**Blocking missing deps:** None. ffmpeg is optional (only needed if the fixture script chooses MP3 source; WAV source avoids it).

**Action item for planner:** Either (a) pick the Common Voice WAV split (if available) to avoid ffmpeg, OR (b) add a README note + CONTRIBUTING.md line "install ffmpeg for fixture regeneration: `brew install ffmpeg`". Regenerating fixtures is a one-time step — contributors don't need ffmpeg to run tests, only to rebuild fixtures.

## Validation Architecture

> `workflow.nyquist_validation: true` in `.planning/config.json` — section required.

### Test Framework

| Property | Value |
|----------|-------|
| Backend framework | pytest 8.3+ (already in Phase 1 pyproject.toml) |
| Backend config | `backend/pyproject.toml` `[tool.pytest.ini_options]` — `asyncio_mode = "auto"` already set |
| Async WebSocket tests | Starlette `TestClient.websocket_connect()` (sync API; works inside pytest-asyncio because it uses its own event loop) [CITED: starlette.io/testclient] |
| Quick run | `cd backend && uv run pytest tests/stt -x --ignore=tests/stt/test_wer_baseline.py` |
| Full suite | `cd backend && uv run pytest tests/` (includes the 30-sample WER batch) |
| CI full suite | `ubuntu-latest`: full pytest including WER batch (downloads fixtures via cache) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| STT-01 | Model loads once at lifespan startup | behavioral (integration) | `uv run pytest tests/stt/test_lifespan.py::test_model_loaded_once -x` | ❌ Wave 0 |
| STT-02a | VAD detects speech onset on synthetic PCM | unit | `uv run pytest tests/stt/test_vad_streaming.py::test_vad_start_event -x` | ❌ Wave 0 |
| STT-02b | VAD detects speech end after silence | unit | `uv run pytest tests/stt/test_vad_streaming.py::test_vad_end_event -x` | ❌ Wave 0 |
| STT-03a | WS upgrade succeeds, `ready` event received | structural | `uv run pytest tests/stt/test_ws_handshake.py -x` | ❌ Wave 0 |
| STT-03b | Binary PCM from fixture produces ≥1 partial within ~1s sim-time | behavioral | `uv run pytest tests/stt/test_ws_pcm_roundtrip.py::test_partial_emitted -x` | ❌ Wave 0 |
| STT-04 | Final event emitted on VAD end with non-empty text | behavioral | `uv run pytest tests/stt/test_ws_pcm_roundtrip.py::test_final_emitted -x` | ❌ Wave 0 |
| STT-05a | `normalise_hebrew` handles NFC/niqqud/punctuation | unit | `uv run pytest tests/stt/test_wer_hebrew.py -x` | ❌ Wave 0 |
| STT-05b | WER on 30-sample fixture ≤ recorded baseline + 3pp grace | regression (batch) | `uv run pytest tests/stt/test_wer_baseline.py -x` | ❌ Wave 0 |
| STT-06 | `stt_latency_ms` captured + logged + SQLite row present | contract + integration | `uv run pytest tests/stt/test_ws_pcm_roundtrip.py::test_latency_logged -x` | ❌ Wave 0 |
| —     | Event schema roundtrips through pydantic (partial/final/error discriminator) | contract | `uv run pytest tests/stt/test_events_schema.py -x` | ❌ Wave 0 |
| —     | Mid-utterance client disconnect frees resources (no VAD iterator leaked) | chaos | `uv run pytest tests/stt/test_chaos_disconnect.py -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `cd backend && uv run ruff check . && uv run mypy src && uv run pytest tests/stt -x --ignore=tests/stt/test_wer_baseline.py` (fast: excludes the 30-sample batch)
- **Per wave merge:** full backend suite including `test_wer_baseline.py` (this re-runs the 30 transcribes on CI — ~2-3 min on ubuntu-latest CPU with int8; measured once at Wave 0 to confirm)
- **Phase gate:** All tests green + WER baseline recorded in STATE.md at phase transition.

### Nyquist Validation Dimensions

1. **Structural** — module layout (`backend/src/receptra/stt/*.py`, `backend/tests/stt/*`), fixture presence (`fixtures/he_cv_30/*.wav` + `*.txt`), WS endpoint mounted at `/ws/stt`.
2. **Behavioral** — binary PCM in → partial events + final event out on the wire; loguru JSON log lines asserted present.
3. **Contract** — pydantic event schema roundtrips; JSON `type` discriminator distinguishes partial/final/error/ready.
4. **Chaos** — mid-utterance WebSocket disconnect: no VAD iterator leaked (`weakref`-check), no SQLite row half-written, no orphaned transcribe thread. Test explicitly: open WS → send partial audio → client-side close → assert server-side cleanup within 500ms.
5. **Regression** — WER baseline recorded at Wave 0; subsequent runs assert `wer ≤ baseline + 0.03` (3 percentage-point grace). Also: latency regression — p95 `stt_latency_ms` ≤ Phase 2 baseline + 30% grace (guards against a dep upgrade silently slowing STT).

### Wave 0 Gaps

Files / infrastructure that MUST be created in Wave 0 before the rest of Phase 2 can validate:

- [ ] `backend/src/receptra/lifespan.py` — NEW: whisper + vad singleton loader
- [ ] `backend/src/receptra/stt/__init__.py` — NEW
- [ ] `backend/src/receptra/stt/events.py` — NEW: pydantic schema
- [ ] `backend/src/receptra/stt/engine.py` — NEW: `transcribe_hebrew(audio_f32)` with locked params
- [ ] `backend/src/receptra/stt/pipeline.py` — NEW: WebSocket handler loop
- [ ] `backend/src/receptra/stt/wer.py` — NEW: `normalise_hebrew` + `compute_wer`
- [ ] `backend/src/receptra/stt/metrics.py` — NEW: UtteranceMetrics + loguru + SQLite insert stub
- [ ] `backend/src/receptra/main.py` — EDIT: mount `/ws/stt`, switch to `lifespan=`, remove `@app.on_event`
- [ ] `backend/src/receptra/config.py` — EDIT: add 7 new Settings fields
- [ ] `backend/pyproject.toml` — EDIT: add 4 runtime deps + 2 dev deps
- [ ] `backend/tests/stt/__init__.py` — NEW
- [ ] `backend/tests/stt/fixtures/he_cv_30.jsonl` — NEW: 30-row fixture manifest
- [ ] `backend/tests/stt/fixtures/he_cv_30/*.wav` + `*.txt` — NEW: 30 fixtures via fetch script
- [ ] `backend/tests/stt/conftest.py` — NEW: shared fixtures (loaded whisper model for real-transcribe tests; mocked for unit tests)
- [ ] `backend/tests/stt/test_*.py` — 7 new test files per §Phase Requirements → Test Map
- [ ] `scripts/fetch_stt_fixtures.py` — NEW: one-time fixture downloader
- [ ] `.env.example` — EDIT: add 7 new `RECEPTRA_*` vars
- [ ] `docker-compose.yml` — EDIT: add `./data:/app/data:rw` volume
- [ ] `scripts/check_licenses.sh` — VERIFY allowlist covers torch + onnxruntime license strings (OPEN-4)

**Wave 0 SPIKE task (runs before anything else):**
- [ ] `scripts/spike_stt_latency.py` — load model, warmup once, transcribe a 2s Hebrew fixture, print p50/p95 wall-clock ms. Output locks OPEN-2 decision before plumbing begins.

## Security Domain

> `security_enforcement` not explicitly false in `.planning/config.json` — include section.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Local-only single-user; no auth in v1 — documented as known limitation |
| V3 Session Management | partial | WebSocket has implicit per-connection session; no cookies/JWT |
| V4 Access Control | no | Single-user OSS self-host; not multi-tenant |
| V5 Input Validation | **yes** | PCM frame size validation (must be exactly 1024 bytes); pydantic schema on text frames; reject oversized binary frames; rate-limit per-connection frame rate (drop >100 fps as abusive) |
| V6 Cryptography | no | No crypto ops in Phase 2 |
| V12 File Handling | partial | Fixture WAVs live in-repo; no user file uploads in Phase 2 |
| V13 API | yes | WebSocket endpoint follows explicit schema (§8); reject malformed text frames with `{"type":"error","code":"protocol_error"}` |

### Known Threat Patterns for {FastAPI WebSocket + model inference}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Oversized binary frames (DoS via memory) | Denial of service | `websocket_max_size=65536` on FastAPI WS; reject frames ≠ 1024 bytes with error |
| Flooding transcribes (DoS via CPU) | Denial of service | Single-worker thread pool for STT (already recommended in Pitfall #5); per-connection soft limit on concurrent utterances (should be impossible with VAD gating anyway — VAD can't open a new utterance while one is active) |
| Malicious PCM designed to trigger Whisper hallucination for prompt-injection downstream | Tampering | Phase 2 only transcribes → text. Prompt injection belongs to Phase 3 LLM mitigations. |
| WebSocket-level MITM | Information disclosure | v1 is local-only (localhost); no WSS required. Document that LAN deployments require reverse proxy with TLS (Phase 7 docs) |
| Path traversal in fixture loader | Tampering | `scripts/fetch_stt_fixtures.py` pins exact file IDs from HF; no user-supplied paths |
| Audit-log PII leak | Information disclosure | Hebrew transcripts ARE PII (contain business content). Audit SQLite is local-only, filesystem-permissioned. Document that the audit DB contains transcripts → back up securely, do NOT ship in bug reports. |

**Security non-goals for Phase 2** (documented for transparency):
- No authentication on `/ws/stt` — local-only single-user
- No WSS — local http is fine
- No rate limiting at HTTP level — backend has single consumer
- No audit-log encryption at rest — user's filesystem permissions are the boundary

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `ivrit-ai/whisper-large-v3-turbo-ct2` achieves 12-25% WER on conversational Hebrew | §9 WER, §10 fixture | Baseline number is for logging, not gating — low risk. Wave 0 spike measures actual. |
| A2 | faster-whisper `int8` on M2 CPU hits "~500ms" for a 2-3s Hebrew utterance | §2 TL;DR, §11 latency | **Medium-high risk.** Drives the partial-cadence decision. Wave 0 spike measures first; plan locks based on measurement. |
| A3 | CTranslate2 arm64 wheel works inside `python:3.12-slim` arm64 Docker | §Recommended Dependencies | Verified by session install on macOS arm64. Docker arm64 wheel is pulled from the same manylinux_2_27_aarch64. Low risk. |
| A4 | Silero VAD v6.2.1 VADIterator API is unchanged from v5.x | §4 | Verified in Context7 docs + session install. Low risk. |
| A5 | Pytest + Starlette TestClient.websocket_connect handles binary frames correctly | §Validation | Well-documented in Starlette docs + FastAPI WS testing guide. Low risk. |
| A6 | Common Voice he-25.0 has WAV or easily-resampleable clips usable as fixtures | §10 | Verified dataset exists; format specifics may need ffmpeg. Medium-low risk. Fallback: record 30 short clips ourselves. |
| A7 | torch's license string passes the Phase 1 `check_licenses.sh` allowlist | §Recommended Dependencies, OPEN-4 | **Medium risk.** Planner's Wave 0 should verify before locking deps. If fail, extend allowlist. |
| A8 | `condition_on_previous_text=False` is safe for batch WER eval too | §7 | Possibly suboptimal for long-form, but fine for our ≤10s fixture clips. Low risk. |
| A9 | 30 samples is a statistically reasonable baseline size for Phase 2 | §10 | Acknowledged small; sufficient for "trend" detection in CI regression. For scientific comparison we'd want 200+. Acceptable for Phase 2 scope. |
| A10 | Hebrew fixture WAV files total ~1.5 MB, committable without LFS | §10 | Low risk. If larger, enable `.gitattributes` LFS for `*.wav`. |
| A11 | FastAPI lifespan + async WebSocket handler + `asyncio.to_thread` is sufficient concurrency model for Phase 2 | §3, Pitfall #5 | Low risk for single local user. Multi-client concurrency is Phase 5's concern. |
| A12 | ivrit-ai model ships with `tokenizer.json` compatible with faster-whisper 1.2.1's tokenizer module | §2 | Would have surfaced in Phase 1's Plan 01-05 (`hf download`) if broken. Low risk. |

## Sources

### Primary (HIGH confidence)

- [faster-whisper on PyPI](https://pypi.org/project/faster-whisper/) — version 1.2.1, Python ≥3.9
- [faster-whisper GitHub releases](https://github.com/SYSTRAN/faster-whisper/releases) — release history
- [SYSTRAN/faster-whisper repo + Context7](https://context7.com/systran/faster-whisper) — WhisperModel + VAD + transcribe options + logging
- [SYSTRAN/faster-whisper issue #911 — unsupported device mps](https://github.com/SYSTRAN/faster-whisper/issues/911) — confirms no Metal/MPS path
- [SYSTRAN/faster-whisper issue #477 — VAD default parameter differences](https://github.com/SYSTRAN/faster-whisper/issues/477)
- [SYSTRAN/faster-whisper issue #1249 — different VAD behaviours (built-in vs external Silero)](https://github.com/SYSTRAN/faster-whisper/issues/1249)
- [silero-vad on PyPI](https://pypi.org/project/silero-vad/) — version 6.2.1 (2026-02-24)
- [snakers4/silero-vad repo + Context7](https://context7.com/snakers4/silero-vad) — VADIterator streaming pattern + load_silero_vad
- [snakers4/silero-vad discussion #471 — v5 release notes](https://github.com/snakers4/silero-vad/discussions/471) — fixed 512-sample window
- [ivrit-ai/whisper-large-v3-turbo-ct2 model card](https://huggingface.co/ivrit-ai/whisper-large-v3-turbo-ct2) — Apache 2.0, language="he" mandatory, translate broken
- [ivrit-ai/whisper-large-v3-turbo model card](https://huggingface.co/ivrit-ai/whisper-large-v3-turbo) — training data hours, leaderboard reference
- [ivrit.ai training-whisper blog 2025](https://www.ivrit.ai/en/2025/02/13/training-whisper/) — training methodology + catastrophic-forgetting mitigations
- [jiwer on PyPI](https://pypi.org/project/jiwer/) — version 4.0.0
- [jitsi/jiwer GitHub](https://github.com/jitsi/jiwer) — WER/CER API + transforms
- [FastAPI WebSockets docs](https://fastapi.tiangolo.com/advanced/websockets/) — send_bytes/receive_bytes
- [FastAPI lifespan events docs](https://fastapi.tiangolo.com/advanced/events/) — asynccontextmanager pattern
- [FastAPI testing WebSockets](https://fastapi.tiangolo.com/advanced/testing-websockets/) — TestClient.websocket_connect
- [FastAPI discussion #9604 — on_event + lifespan mutual exclusion](https://github.com/fastapi/fastapi/discussions/9604)
- [Starlette TestClient docs](https://www.starlette.io/testclient/) — send_bytes / receive_json
- [OpenNMT CTranslate2 Whisper docs](https://opennmt.net/CTranslate2/python/ctranslate2.models.Whisper.html) — arm64 backends, compute_types
- [Mozilla Common Voice Hebrew (cv-corpus-25.0)](https://mozilladatacollective.com/datasets/cmn29vgka017lo107v8ebc8r1) — 5524 clips, 6.98 hours, CC0
- [Phase 1 research doc](.planning/phases/01-foundation/01-RESEARCH.md) — Phase 1 stack decisions, Pipecat deferral

### Secondary (MEDIUM confidence)

- [saytowords.com — Real-time streaming with Whisper (2026)](https://www.saytowords.com/blogs/Real-Time-Streaming-with-Whisper/) — incremental re-transcribe patterns
- [ufal/whisper_streaming](https://github.com/ufal/whisper_streaming) — LocalAgreement policy reference (not used in Phase 2 but documented as OPEN-1 option B)
- [collabora/WhisperLive](https://github.com/collabora/WhisperLive) — faster-whisper-based streaming server (rejected for Phase 2, see §7)
- [dash0.com — Python logging with Loguru](https://www.dash0.com/guides/python-logging-with-loguru) — serialize=True JSON pattern
- [Mahdi Jafari — FastAPI + Loguru](https://mahdijafaridev.medium.com/log-like-a-legend-power-up-fastapi-with-loguru-for-real-world-logging-bc0f10834eb4) — wiring pattern
- [chariotsolutions — Apple Silicon GPUs, Docker and Ollama: pick two](https://chariotsolutions.com/blog/post/apple-silicon-gpus-docker-and-ollama-pick-two/) — confirms no Metal in Docker; STT inside Docker is CPU int8
- [openai/whisper discussion #1606 — hallucination on no-speech](https://github.com/openai/whisper/discussions/1606)
- [openai/whisper discussion #608 — streaming approaches](https://github.com/openai/whisper/discussions/608)

### Tertiary (LOW confidence — verify at execution time)

- Exact Hebrew WER benchmark numbers for `ivrit-ai/whisper-large-v3-turbo-ct2` — no single published headline; leaderboard page content was not scraped successfully. Baseline will be measured in Wave 0.
- CTranslate2 p95 latency on M2 16GB for a 2-second Hebrew utterance at `int8 / cpu_threads=4` — unmeasured in this research; Wave 0 spike required.
- torch 2.11 license string as reported by `pip-licenses` — unverified against Phase 1 allowlist; OPEN-4 addresses.

## Metadata

**Confidence breakdown:**
- Standard stack (faster-whisper + silero-vad + jiwer + loguru versions, arm64 wheels): **HIGH** — all installed cleanly in-session on Python 3.12 arm64
- Apple Silicon compute path (device=cpu + compute_type=int8): **HIGH** — officially documented, no Metal path exists
- Language pinning + Hebrew params (language="he", condition_on_previous_text=False, beam_size=1): **HIGH** — ivrit-ai model card + Whisper docs
- Silero VAD streaming pattern (VADIterator + 512-sample window): **HIGH** — Context7 + official README
- Partial-transcript strategy (incremental re-transcribe): **MEDIUM-HIGH** — widely-used community pattern; LOW on exact cadence (depends on measured M2 latency)
- WebSocket wire format (16kHz mono int16 LE 1024-byte frames): **HIGH** — standard
- WER tool (jiwer 4.0) + Hebrew normalisation: **MEDIUM** — pattern is defensible but "canonical Hebrew ASR eval" isn't a single specified thing
- Hebrew WER baseline number: **LOW** — no published number for this specific variant on short conversational clips; will measure
- Latency budget adherence on M2 (~1s partials, sub-500ms STT): **LOW until Wave 0 spike** — flagged as OPEN-2

**Research date:** 2026-04-24
**Valid until:** 2026-05-24 (30 days — faster-whisper + silero-vad are stable; re-verify before Phase 2 execution if >30 days elapse)

---

## RESEARCH COMPLETE

**Phase:** 02 — Hebrew Streaming STT
**Confidence:** HIGH (stack + integration) / MEDIUM (Hebrew WER target, Mac latency budget)

### Key Findings

1. **Stack is pin-ready:** faster-whisper 1.2.1 + silero-vad 6.2.1 + jiwer 4.0 + loguru 0.7.3 all install on Python 3.12 arm64 macOS with correct CTranslate2 4.7.1 arm64 wheel (verified in-session). All Apache-2.0 / MIT / BSD — compatible with Phase 1 CI allowlist modulo a Wave 0 spot-check on torch.
2. **Apple Silicon path confirmed: `device="cpu", compute_type="int8", cpu_threads=4`.** faster-whisper does NOT support MPS/Metal; CTranslate2 arm64 CPU backend via Apple Accelerate is the correct path. int8 gives ~4x over float32.
3. **Hebrew config is non-negotiable:** `language="he"` on every transcribe call; ivrit-ai broke language-auto-detect and the translate task during fine-tuning. `condition_on_previous_text=False` for live re-transcribes; `beam_size=1`, `temperature=0.0`.
4. **VAD: external Silero VADIterator, NOT faster-whisper's built-in** `vad_filter`. Live streaming needs per-chunk events (start/end); faster-whisper's VAD is a batch pre-filter. Wire contract: 512-sample windows = 1024-byte binary WS frames = 32 ms of 16 kHz mono int16 little-endian audio.
5. **Partial-transcript strategy: incremental re-transcribe on a VAD-gated buffer,** ~700ms cadence. No WhisperLive or ufal/whisper_streaming dep — just a ~100 LOC asyncio loop. Flicker accepted; LocalAgreement-2 deferred as OPEN-1.
6. **FastAPI lifespan refactor required:** replace existing `@app.on_event("startup")` in `main.py` with `lifespan=` pattern; load whisper + silero VAD singletons on `app.state`. One warmup transcribe before `yield`.
7. **WER eval: jiwer 4.0 with Hebrew NFC + niqqud-stripped normalisation.** Seed 30 fixtures from Mozilla Common Voice Hebrew 25.0 (CC0). Record WER + CER as informational baseline, do NOT gate Phase 2 on a specific number.
8. **Latency instrumentation: per-stage monotonic clocks** → structured JSON log line + SQLite audit row (stub table; Phase 5 owns final INT-05 schema). STT-06 metric = `t_final_ready - t_speech_end`.
9. **A Wave 0 spike to measure first-transcribe latency on M2 16GB is the highest-priority task** — it locks the partial-cadence + validates OPEN-2 before plumbing.
10. **Non-goals (explicit):** no Pipecat, no LLM, no RAG, no frontend, no full INT-05 audit schema, no Prometheus, no WhisperLive, no diarisation. All deferred to later phases.

### File Created

`.planning/phases/02-hebrew-streaming-stt/02-RESEARCH.md`

### Confidence Assessment

| Area | Level | Reason |
|------|-------|--------|
| Standard Stack (versions, arm64 wheels, licenses) | HIGH | Installed cleanly in-session on Python 3.12 arm64 macOS |
| Apple Silicon compute path | HIGH | Officially no MPS support; int8 CPU is canonical |
| Hebrew transcribe params | HIGH | ivrit-ai model card explicit |
| VAD streaming API | HIGH | Context7 + official README corroborate |
| WebSocket wire format | HIGH | Silero v5+ fixed window size forces 512 samples |
| Event schema | HIGH | Standard pydantic discriminated union |
| WER tooling | MEDIUM | jiwer usage fine; Hebrew-normalisation details are our choice |
| WER target number | LOW | No single published baseline for this model/variant/short-clip combo — will measure in Wave 0 |
| M2 latency budget feasibility | LOW | Unmeasured in-session; Wave 0 spike required to lock OPEN-2 |
| License gate compatibility | MEDIUM | torch + onnxruntime strings need verification against allowlist (OPEN-4) |
| Pipecat integration path | HIGH | Phase 1 research already deferred cleanly |

### Open Questions (tracked as OPEN-1 .. OPEN-8 above)

1. Partial-flicker acceptable vs LocalAgreement-2 policy (recommend A)
2. **Wave 0 spike to measure M2 int8 latency before plumbing** (critical)
3. Whisper.cpp + Core ML fallback (document only, don't build)
4. License allowlist check for torch + onnxruntime strings
5. WS endpoint path: `/ws/stt` vs `/ws` (recommend `/ws/stt`)
6. Frame cadence: 512 samples = 32 ms (forced by Silero)
7. WER baseline as gate vs informational (recommend informational)
8. SQLite `data/` directory mount in docker-compose (recommend add)

### Ready for Planning

Research complete. Planner can now create PLAN.md files. Suggested plan decomposition (planner's discretion):

- **Plan 02-01 (Wave 0 spike):** Latency spike + dep pin + license-allowlist verification + fixture fetch script
- **Plan 02-02 (Wave 0 scaffolding):** `lifespan.py` + `config.py` edits + `stt/` module skeletons + `tests/stt/` skeletons
- **Plan 02-03:** VAD + partial re-transcribe pipeline (`stt/pipeline.py`, `stt/engine.py`) with unit + behavioral tests
- **Plan 02-04:** WER eval module (`stt/wer.py`) + 30-sample batch regression test
- **Plan 02-05:** Latency instrumentation + SQLite stub + loguru JSON config + integration test
- **Plan 02-06 (Polish / gate):** Chaos disconnect test, docker-compose volume add, README/docs update, WER + latency baseline committed to STATE.md

Planner is free to decompose differently; all six requirements (STT-01..06) are mapped to the files above.
