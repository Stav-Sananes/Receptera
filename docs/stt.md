# Hebrew Streaming STT (Phase 2)

Receptra's Phase 2 ships a local-only Hebrew speech-to-text WebSocket at
`/ws/stt`. No cloud, no telephony, no auth — your machine, one process,
one WebSocket. This page is the user/contributor contract: wire format,
event schema, latency baseline, audit log + PII rules, and a
troubleshooting checklist.

## Overview

- **Transport:** WebSocket on `/ws/stt` (browser-native, dev proxy via Vite).
- **STT engine:** [`faster-whisper`](https://github.com/SYSTRAN/faster-whisper)
  running the [`ivrit-ai/whisper-large-v3-turbo-ct2`](https://huggingface.co/ivrit-ai/whisper-large-v3-turbo-ct2)
  Hebrew checkpoint, loaded once at startup via the FastAPI lifespan
  context manager (Pitfall #1 mitigated).
- **VAD:** [`silero-vad`](https://github.com/snakers4/silero-vad) v6 in
  TorchScript mode (no ONNX runtime); per-WebSocket wrapper isolates
  state across concurrent connections.
- **Language:** Hebrew is hard-coded in the transcribe wrapper
  (`receptra.stt.engine.transcribe_hebrew`); switching languages is a
  Phase 7 concern.
- **Hardware target:** Apple Silicon M2 16GB+ (CPU path via CT2 int8;
  GPU/Metal path is deferred to Phase 7).
- **Run command:** `make up` — brings up the full Compose stack with
  Ollama on the host (see `docs/docker.md`).

## Wire Contract

The client opens a WebSocket to `ws://localhost:8080/ws/stt` (or via
the Vite dev proxy at `ws://localhost:5173/ws/stt`).

**Client → server:** binary WebSocket frames carrying raw PCM. Every
frame must be:

- **exactly 1024 bytes**,
- **int16 little-endian**,
- **16 kHz mono**,
- **32 ms of audio per frame** (1024 / 2 / 16000 = 0.032 s).

Frames that violate any of these constraints close the connection with
WebSocket code **1007 (Invalid Frame Payload Data)** and a
`type=="error", code=="protocol_error"` JSON event.

**Server → client:** UTF-8 JSON text frames, one event per frame. The
schema is the discriminated union published by `receptra.stt.events`.

## Event Schema

Four event types, discriminated on the `type` field:

```json
// Sent immediately after WebSocket accept.
{"type": "ready", "model": "ivrit-ai/whisper-large-v3-turbo-ct2",
 "sample_rate": 16000, "frame_bytes": 1024}

// Emitted ≥1× per active utterance, cadence locked by stt_partial_interval_ms.
{"type": "partial", "text": "שלום",
 "t_speech_start_ms": 12345, "t_emit_ms": 12999}

// Emitted exactly once per utterance on VAD end-of-speech.
{"type": "final", "text": "שלום עולם",
 "t_speech_start_ms": 12345, "t_speech_end_ms": 14200,
 "stt_latency_ms": 380, "duration_ms": 1855}

// Sent on protocol / model / VAD failure. The 3-code allowlist is
// research-locked; adding a 4th requires a plan amendment.
{"type": "error", "code": "protocol_error", "message": "frame size 512 != 1024"}
```

All timestamps (`t_*_ms`) are **monotonic** milliseconds — they are
unaffected by NTP slew or wall-clock changes. Audit-only `ts_utc` is a
separate ISO-8601 wall-clock string used solely for human-readable
ordering inside the SQLite audit log.

## Latency Baseline

The end-to-end metric of record is **`stt_latency_ms`** =
`t_final_ready - t_speech_end` — the time between Silero declaring
end-of-speech and the server having a full Hebrew transcript ready to
send. This number is captured per utterance and:

1. Logged as a single-line loguru JSON event (`event="stt.utterance"`),
2. Persisted to the local SQLite audit table (see next section), and
3. Returned inline on the `final` event itself.

Phase 2 ships **provisional** latency parameters from the Wave-0 spike
(see [`02-01-SPIKE-RESULTS.md`](../.planning/phases/02-hebrew-streaming-stt/02-01-SPIKE-RESULTS.md)):

- `stt_partial_interval_ms = 700` — the audio-time gap between partials.
- Partial cadence is gated on **accumulated audio time**, not wall-clock
  time, so a non-real-time producer (TestClient bursting frames, an
  offline batch test) still fires partials per the contract.

Real M2 hardware p50/p95 numbers will be filled in once a Hebrew
contributor with the model weights and Common Voice 25.0 access runs
the WER + latency harness end-to-end. As of this writing the baseline
is **UNMEASURED** on reference hardware (RESEARCH §11 + Plan 02-06
follow-up).

## Audit Log + PII Warning

A SQLite stub table `stt_utterances` is created lazily at the path in
`RECEPTRA_AUDIT_DB_PATH` (default `/app/data/audit.sqlite` inside the
backend container, mapped to `./data/audit.sqlite` on the host via the
`./data:/app/data:rw` Docker Compose volume). Phase 5 (INT-05) extends
the schema in place via `ALTER TABLE ADD COLUMN`.

Schema (RESEARCH §11, verbatim):

```sql
CREATE TABLE IF NOT EXISTS stt_utterances (
    utterance_id TEXT PRIMARY KEY,
    ts_utc TEXT NOT NULL,
    duration_ms INTEGER NOT NULL,
    stt_latency_ms INTEGER NOT NULL,
    transcribe_ms INTEGER NOT NULL,
    partials_emitted INTEGER NOT NULL,
    text TEXT NOT NULL,
    wer_sample_id TEXT
);
```

**PII WARNING — read this before sharing logs.** Every Hebrew transcript
your machine processes lands in `./data/audit.sqlite`. That file is:

- **Sensitive.** It contains every word every caller has said while you
  were running Receptra. Treat it like the call recordings you would
  treat under any privacy regulation that applies in your jurisdiction.
- **Excluded from git.** `data/` is gitignored and will not be
  accidentally committed. Do not work around this.
- **NOT for bug reports.** When filing an issue or attaching diagnostic
  artifacts, **do not attach the SQLite file**. Run the troubleshooting
  steps below and share log lines with redaction enabled (the default).
- **Not auto-rotated.** Phase 2 is a stub; Phase 5 (INT-05) owns
  retention and `VACUUM` policy. Periodically delete or archive the
  file as your privacy posture requires.

The structured loguru log line that pairs with each row **redacts the
transcript body by default**. Only metadata
(`utterance_id`, `stt_latency_ms`, `partials_emitted`, `text_len_chars`,
…) flows into log aggregators. To opt INTO logging the raw text body —
useful only for local debugging — set
`RECEPTRA_STT_LOG_TEXT_REDACTION_DISABLED=true`. This **weakens the PII
boundary** documented in this section; do not enable it in production
deployments or shared environments.

## Running the WER Eval

WER (word error rate) is measured offline by a separate harness covered
in [`docs/stt-eval.md`](./stt-eval.md). It uses the same
`receptra.stt.engine.transcribe_hebrew` wrapper as the live hot path
(no kwarg drift), runs against a 30-clip Common Voice 25.0 Hebrew
fixture set, and emits a JSON report with `wer_p50/p95` and
`cer_p50/p95`. The regression test in `backend/tests/stt/test_wer_baseline.py`
catches dependency drift but is not an absolute accuracy floor.

## Known Limitations (Phase 2 Scope)

- **No Pipecat yet.** The pipeline is a hand-rolled VAD-gated re-transcribe
  loop. Phase 5 (INT-05) replaces it with Pipecat for back-pressure +
  RAG/LLM streaming.
- **No authentication.** The WebSocket is open to any client that can
  reach the port. Receptra v1 is a single-user local self-host; multi-user
  auth is a v2 concern.
- **CPU-only on Apple Silicon.** `faster-whisper` does not yet have a
  Metal/MPS path; CT2 runs on the M2 performance cores at int8. Phase 7
  may revisit `whisper.cpp` + Core ML.
- **Partial flicker is acceptable.** RESEARCH OPEN-1 Option A: each
  partial is a fresh transcribe of the speech-buffer prefix, so the
  text can change between partials. The frontend is responsible for
  rendering this as a single mutating "live caption" line.
- **Multi-utterance per connection is best-effort.** v1 closes the WS
  after one final; the loop nominally supports more but multi-utterance
  streaming is a Phase 7 concern.

## Troubleshooting

### "WebSocket closes immediately with `protocol_error`"
The server got a binary frame whose size is not exactly 1024 bytes.
Check that the client is encoding **int16 LE** (not float32 or int24)
and that frame chunking matches `frame_bytes` from the `ready` event.
A common JS pitfall: `Uint8Array.buffer.byteLength` vs the slice length
when re-using a single underlying ArrayBuffer.

### "Connected fine but no `partial` events arrive"
Silero VAD has not crossed its speech-probability threshold. Quiet
microphones or low-amplitude room audio can sit at probability ~0.3,
below the default 0.5 gate. Try lowering `RECEPTRA_VAD_THRESHOLD` (e.g.
0.3) for a cheap mic, then back up once the contract holds. Pure
sinusoidal test tones do **not** register as speech against Silero v5;
use real voice or the FM-modulated harmonic stack from
`backend/tests/stt/test_vad_streaming.py` if you need a deterministic
synthetic input.

### "First request feels slow"
The lifespan startup runs a Whisper warmup transcribe before the app
yields (Pitfall #7), so the first WebSocket should NOT pay the CT2 JIT
cost. If you still see a 2-3× spike on the first real utterance, check
that `app.state.warmup_complete is True` after lifespan startup.

### "I see Hebrew text in my logs and I do not want it there"
Confirm `RECEPTRA_STT_LOG_TEXT_REDACTION_DISABLED` is `false` (the
default). Confirm no other logger outside `receptra.stt.metrics.log_utterance`
is emitting the transcript. The audit DB itself is the canonical
PII-bearing surface; it intentionally writes the body.

### "I want to clear the audit log"
Stop the backend, then `rm ./data/audit.sqlite`. The next WebSocket
connection lazily re-creates the table via
`receptra.stt.audit.init_audit_db`.
