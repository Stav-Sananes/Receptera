"""FastAPI lifespan: load Whisper + Silero VAD singletons, warmup, yield.

RESEARCH §3/§5 mandate singleton loading at app startup; Pitfall #1 warns
that ``@app.on_event + lifespan=`` silently drops the startup hook; Pitfall
#7 mandates a warmup transcribe before ``yield`` so the first WebSocket
request does not pay the CT2 JIT warmup cost (2-3x latency spike).

Published contracts (consumed by downstream plans):

* ``app.state.whisper: WhisperModel`` — read by Plan 02-04 WebSocket handler.
* ``app.state.vad_model`` — the raw Silero model; Plan 02-03 constructs
  per-connection ``VADIterator`` instances wrapping this singleton.
* ``app.state.warmup_complete: bool`` — True after the warmup transcribe.
"""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
from fastapi import FastAPI
from faster_whisper import WhisperModel
from loguru import logger
from silero_vad import load_silero_vad

from receptra.config import settings
from receptra.stt.engine import transcribe_hebrew


def _configure_logging() -> None:
    """Install loguru as the single logging sink with JSON serialization.

    RESEARCH §11: one JSON line per event is the audit-log contract consumed
    by Plan 02-06 + Phase 5 INT-05 audit log.
    """
    logger.remove()
    logger.add(
        sys.stderr,
        serialize=True,
        level=settings.log_level.upper(),
        backtrace=False,
        diagnose=False,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Load STT + VAD models once at startup; yield; graceful shutdown."""
    _configure_logging()

    model_path = Path(settings.model_dir) / settings.whisper_model_subdir
    logger.bind(event="stt.lifespan").info(
        {
            "msg": "loading whisper",
            "model_path": str(model_path),
            "compute_type": settings.whisper_compute_type,
            "cpu_threads": settings.whisper_cpu_threads,
            "model_dir": settings.model_dir,
            "ollama_host": settings.ollama_host,
            "chroma_host": settings.chroma_host,
        }
    )
    whisper = WhisperModel(
        str(model_path),
        device="cpu",
        compute_type=settings.whisper_compute_type,
        cpu_threads=settings.whisper_cpu_threads,
        num_workers=1,
    )

    logger.bind(event="stt.lifespan").info({"msg": "loading silero vad"})
    # ONNX=False uses the TorchScript path; JIT on Apple Silicon is fine and
    # sidesteps onnxruntime arm64 oddities (Pitfall #8).
    vad_model = load_silero_vad(onnx=False)

    # Warmup transcribe (Pitfall #7) — 1 second of silence through the same
    # Hebrew-locked wrapper the live hot path uses. This primes the CT2
    # internal buffers + kernel compilation so the first real WebSocket
    # request lands inside the latency budget.
    logger.bind(event="stt.lifespan").info({"msg": "whisper warmup transcribe"})
    warmup_audio = np.zeros(16000, dtype=np.float32)  # 1 s @ 16 kHz
    transcribe_hebrew(whisper, warmup_audio)

    app.state.whisper = whisper
    app.state.vad_model = vad_model
    app.state.warmup_complete = True

    logger.bind(event="stt.lifespan").info({"msg": "receptra STT ready"})
    try:
        yield
    finally:
        logger.bind(event="stt.lifespan").info({"msg": "receptra STT shutting down"})
        # CT2 + silero-vad carry no explicit close contract; GC handles cleanup.
