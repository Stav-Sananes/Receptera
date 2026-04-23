# External Plan Reference (Imported 2026-04-23)

*Source: user-supplied implementation blueprint for a full voice receptionist MVP. NOT v1 scope — saved here for harvesting reusable technical patterns into Milestone 1 phases, and as a reference when Milestone 2 (autonomous voice + TTS) opens.*

## Import Verdict

Blocked by 6 conflicts against locked v1 scope. See `/gsd-import` report (2026-04-23). Plan describes autonomous voice receptionist with Kokoro+Edge-TTS, LiveKit SFU, CUDA, Qwen-primary, HTML+Alpine admin UI, multi-tenancy. v1 locked to Hebrew co-pilot, DictaLM primary, Apple Silicon/Metal, React+Vite sidebar, single-tenant, no TTS.

## Harvestable for v1 (by phase)

### Phase 1: Foundation
- Docker Compose service topology (ollama, chromadb, backend, frontend) — adapt to arm64/Metal, drop CUDA base images and NVIDIA Container Toolkit config
- `make up / down / logs / ingest / test` Makefile pattern
- `.env.example` + gitignored `.env` split; healthcheck + `service_healthy` depends_on chain
- One-shot `ollama-init` container to pull models on first boot — adapt for DictaLM + BGE-M3 + ivrit-ai Whisper
- Monorepo layout (`bot/ widget/ admin/ token-server/ knowledge/ livekit/ scripts/ docs/`) — trim `admin/` and `livekit/` for v1

### Phase 2: Hebrew Streaming STT
- faster-whisper tuning: `compute_type="int8_float16"`, `beam_size=1`, `condition_on_previous_text=False`
- Silero VAD params: `threshold=0.5`, `min_silence_duration_ms=300`, `speech_pad_ms=200`, `min_speech_duration_ms=250`
- ivrit-ai quirk: **always pass `language=Language.HE` explicitly** — fine-tuned model has degraded auto-detection, "translate" task unusable
- MLX alternative on Apple Silicon: `WhisperSTTServiceMLX` with `MLXModel.LARGE_V3_TURBO_Q4` via `pip install "pipecat-ai[mlx-whisper]"`

### Phase 3: Hebrew Suggestion LLM
- Ollama `keep_alive=-1` to pin model in VRAM (avoids cold-start per conversation)
- `"num_predict": 128` for voice-length responses (substitute suggestion-length budget)
- Pipecat `OLLamaLLMService` is thin wrapper over `OpenAILLMService` pointed at `http://localhost:11434/v1` — no API key needed

### Phase 4: Hebrew RAG
- BGE-M3 via Ollama: `ollama pull bge-m3`, then `ollama.embeddings(model="bge-m3", prompt=text)` — dense-only but zero-install
- ChromaDB v2 API endpoint: `/api/v2/heartbeat` (not legacy `/api/v1/heartbeat`)
- Chroma persistence path: `/data` on recent image versions (legacy was `/chroma/chroma`)
- Compose healthcheck: `curl -f http://localhost:8000/api/v2/heartbeat`
- Semantic chunking per-entity for structured KBs beats fixed-token windows (map to Hebrew-aware chunking via `hebrew-nlp-toolkit`)
- Consider Hebrew-specific embedders as evaluation alternatives: `imvladikon/sentence-transformers-alephbert`, `Webiks/Hebrew-RAGbot-KolZchut-QA-Embedder`. Start with BGE-M3, swap only if Recall@5 benchmark demands.

### Phase 5: Hot-Path Integration
- **Pipecat API discipline** — avoid deprecated patterns. Use:
  - `LLMContext` (not `OpenAILLMContext`)
  - `LLMContextAggregatorPair` (not older aggregator classes)
  - `LLMRunFrame` (not `LLMMessagesFrame`)
  - `InterruptionFrame` (not `StartInterruptionFrame`/`StopInterruptionFrame`)
  - `pipecat.transports.<service>.transport` paths (not `pipecat.transports.services.*`)
- `FrameProcessor` three-rule contract: always call `super().__init__`, always `await super().process_frame(frame, direction)` first, **always forward every frame** via `push_frame` — dropping frames deadlocks pipeline
- Custom `RAGProcessor` pattern: intercept `TranscriptionFrame`, inject `[CONTEXT]...[/CONTEXT]` prefix into transcript text before context aggregator — simplest integration point
- VAD tuning: `SileroVADAnalyzer(params=VADParams(stop_secs=0.2))` responsive; `0.5` more natural
- Enable `enable_metrics=True` + `enable_usage_metrics=True` on `PipelineParams` — Pipecat auto-emits `MetricsFrame` with `TTFBMetricsData` usable for latency dashboard
- Per-stage `asyncio.wait_for` timeouts: STT 5s, LLM 8s, RAG 1s. Circuit breaker pattern for Ollama/Chroma outages.
- Correlation: `contextvars.ContextVar("call_id")` + loguru JSON sink

### Phase 6: Frontend
- `getUserMedia` + WebSocket PCM streaming — confirm v1 uses bare WebSocket (not LiveKit SFU). Browser AEC/NS on by default: `audioCaptureDefaults: { autoGainControl, echoCancellation, noiseSuppression }`
- iOS/Safari autoplay quirk: call `startAudio()` inside same click handler that connects — applicable if LiveKit client ever adopted

### Phase 7: Polish & Demo
- Error fallback copy patterns (per-stage canned responses) — adapt to Hebrew
- Load test options: `livekit-cli load-test`, Playwright headless, Pipecat-only throughput benchmarks. Likely skip for v1.

## NOT for v1 (defer M2 or drop)

- Kokoro TTS — English-only, v1 has no TTS
- Edge-TTS — cloud dependency violation, v1 has no TTS
- LiveKit SFU self-host — v1 uses bare WebSocket
- Token-server + per-room JWT — v1 single-tenant, single-session
- Admin setup wizard (6 steps) — out of v1 scope
- Call dashboard + `call_logs` / `turn_logs` SQL tables — audit log in v1 is local SQLite per INT-05, not a dashboard
- Multi-tenancy (per-business Chroma collections, API keys) — v1 single-tenant
- NVIDIA Container Toolkit + CUDA base images — Apple Silicon floor, use Metal
- Qwen 2.5 7B as primary LLM — DictaLM 3.0 primary, Qwen only if DictaLM blocked

## Pitfall Reminders (from plan, direct lift)

1. Pipecat tutorials online heavily use deprecated APIs — verify imports against current release before copy-paste
2. Qwen 2.5 tool-calling via Ollama works but multi-turn accuracy lags GPT-4o/Gemini — validate with evals before trusting for structured suggestion JSON in LLM-04
3. ivrit-ai Whisper requires explicit `language="he"` — auto-detect degraded by fine-tuning
4. `condition_on_previous_text=False` in faster-whisper eliminates a common hallucination class
5. Ollama `keep_alive=-1` prevents weight unload between turns — biggest single latency win after quantization
6. Chroma v2 heartbeat endpoint changed from `/api/v1/heartbeat` to `/api/v2/heartbeat`
7. Chroma persistence volume mount path — `/data` on recent versions, `/chroma/chroma` legacy

## For Milestone 2 (future reference)

When TTS + autonomy open in M2, the plan's voice-bot architecture (LiveKit SFU + Kokoro/Edge-TTS dual-engine + bilingual language router + admin wizard + multi-tenancy + call logging) becomes directly applicable. Re-import at M2 start.
