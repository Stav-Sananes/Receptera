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

    # --- Phase 3 LLM (Hebrew Suggestion Engine) — defaults locked by 03-RESEARCH §6.5 + §3.3 ---
    # Primary Ollama model tag (registered by `make models dictalm`); fallback used
    # only when the primary is missing from `ollama list`.
    llm_model_tag: str = "dictalm3"
    llm_model_fallback: str = "qwen2.5:7b"

    # Generation parameters — temperature=0.0 is the grounding lock (Pitfall E
    # in 03-RESEARCH; deterministic output enables grounded refusal). Override
    # via `RECEPTRA_LLM_TEMPERATURE=...` only for prompt-tuning experiments.
    llm_temperature: float = 0.0
    llm_num_predict: int = 512
    llm_num_ctx: int = 8192
    llm_top_p: float = 0.9

    # AsyncClient request timeout. 30 s absorbs cold-start (~5 s on first call
    # after Ollama process restart) without indefinitely wedging the WS hot path.
    llm_request_timeout_s: float = 30.0

    # System-prompt language. 'he' (Hebrew, default — DictaLM 3.0 is Hebrew-native)
    # vs 'en' (English fallback for Phase 7 A/B). Locked OPEN-LLM-2.
    llm_system_prompt_lang: str = "he"

    # When True, the loguru `event="llm.call"` log line INCLUDES the raw transcript
    # body. Default False — Hebrew transcripts are PII (mirrors stt_log_text_redaction_disabled
    # from Plan 02-06). Enable ONLY for local debugging; weakens the PII boundary
    # documented in docs/llm.md.
    llm_log_text_redaction_disabled: bool = False

    # --- Phase 4 RAG (Hebrew Knowledge Base) — defaults locked by 04-RESEARCH
    # §Cluster 5 + §Hebrew Chunking Strategy + §BGE-M3 Pattern ---

    # Cosine-similarity floor for retrieved chunks. Below this, the chunk is
    # filtered before ChunkRef[] is returned. RESEARCH §Cluster 5: 0.35 is the
    # working default carried over from EXTERNAL-PLAN-REFERENCE.md; the
    # recall@5 eval (Plan 04-06 — RAG-05) is the authoritative tuning lever.
    rag_min_similarity: float = 0.35

    # UI confidence gate (v1.1 F1). Chunks between rag_min_similarity (0.35)
    # and this threshold are passed to the LLM but the frontend renders a
    # "ביטחון נמוך" badge. Set to 0.0 to disable the badge entirely.
    rag_suggestion_threshold: float = 0.65

    # Greedy-chunker target window. RESEARCH §Hebrew Chunking Strategy:
    # 1500 chars ≈ 500 BGE-M3 tokens via the 1-token≈3-Hebrew-char heuristic;
    # validated by Wave-0 spike (scripts/spike_chunk_token_ratio.py) and
    # locked into 04-01-SPIKE-RESULTS.md. Plan 04-06 retunes if recall@5 demands.
    rag_chunk_target_chars: int = 1500

    # Greedy-chunker overlap window. ~200 chars ≈ 65 BGE-M3 tokens (~12% of
    # chunk) — the textbook RAG overlap value per RESEARCH §Hebrew Chunking
    # Strategy citing pinecone.io/learn/chunking-strategies +
    # weaviate.io/blog/chunking-strategies-for-rag.
    rag_chunk_overlap_chars: int = 200

    # BGE-M3 ingest batch size. RESEARCH §BGE-M3 Pattern: 16 keeps memory
    # footprint stable on 16 GB Mac (24 KB input + 64 KB output per batch);
    # 32 risks Ollama context-overflow on docs with ≥32 chunks all >2k tokens.
    # Adjust via RECEPTRA_RAG_EMBED_BATCH_SIZE only if Wave-0 spike pushes higher.
    rag_embed_batch_size: int = 16


settings = Settings()
