"""Runtime configuration loaded from environment variables.

All settings use the ``RECEPTRA_`` prefix. See repo-root ``.env.example``.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Receptra runtime settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="RECEPTRA_",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Phase 1 foundation ---
    model_dir: str = "/models"
    ollama_host: str = "http://host.docker.internal:11434"
    chroma_host: str = "http://chromadb:8000"
    log_level: str = "INFO"

    # --- Phase 2 STT (Hebrew streaming) — defaults locked by RESEARCH §Recommended
    # Dependencies + 02-01-SPIKE-RESULTS.md (partial_interval_decision). ---
    whisper_model_subdir: str = "whisper-turbo-ct2"
    whisper_compute_type: str = "int8"
    whisper_cpu_threads: int = 4
    audit_db_path: str = "./data/audit.sqlite"
    # 700 ms is the provisional lock from 02-01-SPIKE-RESULTS.md (UNMEASURED path,
    # matches RESEARCH §7 Option A). Plan 02-06 re-runs the spike on reference M2
    # hardware and bumps to 1000 if measured p95 > 700.
    stt_partial_interval_ms: int = 700
    vad_threshold: float = 0.5
    vad_min_silence_ms: int = 300
    vad_speech_pad_ms: int = 200

    # When True, the loguru `event="stt.utterance"` log line INCLUDES the raw
    # transcript body. Default False — Hebrew transcripts are PII (RESEARCH
    # §Security Domain). Enable only for local debugging on a developer
    # machine. See docs/stt.md §Audit log + PII warning.
    stt_log_text_redaction_disabled: bool = False


settings = Settings()
