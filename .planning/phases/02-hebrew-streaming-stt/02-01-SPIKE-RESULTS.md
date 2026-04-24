# Phase 2 Plan 02-01 — Wave-0 STT Latency Spike Results

**Status:** UNMEASURED — contributor must run on M2 hardware before Plan 02-04 locks
**Reason:** Model weights not present on the executor filesystem.
Expected location: `/Users/stavnsananes/.receptra/models/whisper-turbo-ct2` (not found).
Run `make models` from repo root (Phase 1 Plan 01-05) to fetch
`ivrit-ai/whisper-large-v3-turbo-ct2` (~1.5 GB) into `$MODEL_DIR`.

**Spike tool:** `scripts/spike_stt_latency.py`
**Model:** `ivrit-ai/whisper-large-v3-turbo-ct2`

## Measurements (UNMEASURED)

| Metric | Value |
|--------|-------|
| `model_load_ms` | UNMEASURED — contributor must run on M2 hardware before Plan 02-04 locks |
| `warmup_transcribe_ms` | UNMEASURED — contributor must run on M2 hardware before Plan 02-04 locks |
| `steady_state_p50_ms` | UNMEASURED — contributor must run on M2 hardware before Plan 02-04 locks |
| `steady_state_p95_ms` | UNMEASURED — contributor must run on M2 hardware before Plan 02-04 locks |
| `iters` | UNMEASURED — contributor must run on M2 hardware before Plan 02-04 locks |

## Decision (contract for Plans 02-02..02-06)

```
partial_interval_decision = 700
```

**Provisional default.** Plan 02-06 will re-run this spike on reference M2
hardware and bump to 1000 if the measured p95 > 700 ms (or escalate OPEN-3 if
p95 > 1000 ms). Until then, downstream plans may assume the RESEARCH default
(700 ms) because (a) it matches RESEARCH §7 Option A, and (b) RESEARCH §1
already verified the packages install cleanly on arm64, so the only unknown is
the steady-state wall-clock — which the fallback re-run in Plan 02-06 will
resolve before Phase 2 exits.

## Host info (executor, not reference hardware)

```json
{
  "platform_machine": "arm64",
  "platform_processor": "arm",
  "mac_ver": "26.4.1",
  "os_cpu_count": 10,
  "python_version": "3.12.13"
}
```

## Reproduction (on reference M2 hardware, AFTER `make models`)

```
cd backend && uv run python ../scripts/spike_stt_latency.py --iters 10
```

## Interpretation

This plan could not run the spike because the model weights were not on disk
at the time of execution. The decision rule (700 / 1000 / BLOCKED) is embedded
in `scripts/spike_stt_latency.py` and will auto-fill correct numbers the next
time a contributor runs the script with the model present. Plan 02-04 should
consume `partial_interval_decision = 700` as a provisional default AND include
a follow-up task in Plan 02-06 that re-executes this spike and commits the
measured numbers back to this file before Phase 2 closes.
