# Receptra Architecture

Placeholder. Full architecture diagram + component descriptions land in Phase 7 (Polish & Demo).

For the current technology stack see:
- `.planning/PROJECT.md` — Core value, constraints, key decisions
- `.planning/ROADMAP.md` — 7-phase Milestone 1 plan
- `CLAUDE.md` — Technology stack reference table

## Component overview (from ROADMAP)

- **STT:** faster-whisper + `ivrit-ai/whisper-large-v3-turbo-ct2` + Silero VAD
- **LLM:** DictaLM 3.0 via Ollama (Qwen 2.5 7B fallback)
- **Embeddings:** BGE-M3 via Ollama
- **Vector DB:** ChromaDB (Docker container, persistent volume)
- **Backend:** Python 3.12 + FastAPI + pydantic-settings + uv
- **Frontend:** React 19 + Vite + TypeScript + Tailwind v4 (RTL)
- **Orchestration:** Docker Compose (arm64)
- **Ollama runtime:** host-native (Metal GPU); backend connects via `host.docker.internal:11434`
