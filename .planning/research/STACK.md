# STACK — Receptra Voice AI Co-pilot

*Source: user-provided deep research report (2025-2026 snapshot) + PROJECT.md decisions. Confidence levels reflect how recently each claim was verified by the source report.*

## Recommended Stack (V1: Hebrew Co-pilot on Apple Silicon)

| Layer | Primary Choice | Fallback | License | Confidence |
|---|---|---|---|---|
| **STT (Hebrew)** | `ivrit-ai/whisper-large-v3-turbo-ct2` via faster-whisper | `ivrit-ai/whisper-large-v3` | Apache 2.0 | High |
| **STT wrapper** | WhisperLive (streaming) + Silero VAD | Whisper-Streaming | MIT | High |
| **LLM (Hebrew)** | DictaLM 3.0 (12B preferred, 1.7B for dev) | Qwen 2.5 7B Instruct | Apache 2.0 / Apache 2.0 | High |
| **LLM runtime** | Ollama (Metal acceleration on Apple Silicon) | llama.cpp directly | MIT | High |
| **Embeddings** | BGE-M3 via Ollama | multilingual-e5-large | MIT | Medium (Hebrew benchmark thin) |
| **Vector DB** | ChromaDB (dev) → Qdrant (production) | pgvector | Apache 2.0 / Apache 2.0 | High |
| **Pipeline** | Pipecat (frame-based streaming) | LiveKit Agents | BSD-2-Clause | High |
| **Transport (v1)** | Browser WebRTC (bare or via LiveKit client) | — | Apache 2.0 | High |
| **Frontend** | React + Vite + TypeScript, TailwindCSS | SvelteKit | MIT | Medium (framework TBD) |
| **Backend shim** | FastAPI (Python) for STT+LLM+RAG orchestration | Node + Express | MIT | High |
| **Deployment** | Docker Compose targeting Apple Silicon (arm64) | Native install script | — | High |

## What NOT to use (and why)

- **OpenAI Whisper (original)** — 4x slower than faster-whisper, no streaming advantage.
- **Kokoro TTS** — English-only, Hebrew not supported. Also we defer TTS entirely in v1.
- **Edge-TTS in v1** — requires internet, unofficial API, and we're not doing TTS in v1.
- **HebTTS / Phonikud** — academic, not production-ready. Revisit in TTS milestone.
- **Vocode / Bolna** — momentum lost / going closed-source per research report.
- **ElevenLabs / commercial TTS** — cloud dependency violates privacy constraint.
- **GPT-4 / Claude / any cloud LLM** — violates "zero cloud dependency" constraint.
- **CUDA-only libraries** — Apple Silicon is the reference floor. Must run via Metal/MLX.
- **Heavy Kubernetes / Helm** — too much for SMB self-host. Docker Compose only.
- **GPL/AGPL deps in the core path** — permissive licensing is a hard constraint.

## Apple Silicon specifics

- Use `llama-cpp-python` or `ollama` with Metal support; verify `METAL=1` compile flag.
- faster-whisper runs via CTranslate2 — verify CPU/Metal path performance on M2. May need to benchmark `whisper.cpp` with Core ML as an alternative since it has Apple Silicon optimizations.
- Target: STT <500ms, LLM TTFT <400ms, total speech→suggestion <2s on M2 16GB.
- Memory budget: 16GB unified memory needs to hold STT model + 7B LLM + embeddings + OS + browser. Q4 quantization is mandatory. Consider DictaLM 1.7B for 16GB devices, 12B for 32GB+.

## Open questions to resolve in Phase 1 research spike

1. Does `whisper.cpp` with Core ML beat faster-whisper on M2 for Hebrew specifically?
2. DictaLM 3.0 — which size actually fits + runs fast on M2 16GB?
3. Does Ollama support DictaLM natively or do we need custom GGUF conversion?
4. Pipecat's streaming on macOS without LiveKit — any gotchas?
5. Does BGE-M3 actually retrieve Hebrew well, or do we need a Hebrew-fine-tuned embedder?
