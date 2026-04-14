# ARCHITECTURE — Receptra V1

## System Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                       Browser (Agent)                      │
│  ┌────────────────────────────────────────────────────┐    │
│  │ React Sidebar                                      │    │
│  │  • Mic capture (getUserMedia)                      │    │
│  │  • Live transcript pane                            │    │
│  │  • Suggestion cards + cited KB snippets            │    │
│  │  • KB upload form                                  │    │
│  └──────────────┬─────────────────────┬───────────────┘    │
│                 │ WebSocket: audio    │ WebSocket: UI      │
└─────────────────┼─────────────────────┼────────────────────┘
                  │                     │
                  ▼                     ▼
┌─────────────────────────────────────────────────────────────┐
│              Receptra Backend (FastAPI, Docker)             │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐    │
│  │ Audio ingest │──│ Silero VAD   │──│ faster-whisper  │    │
│  │ (PCM frames) │  │ endpointing  │  │ ivrit.ai turbo  │    │
│  └──────────────┘  └──────────────┘  └────────┬────────┘    │
│                                               │             │
│                              partial transcripts            │
│                                               ▼             │
│  ┌───────────────────────┐   ┌──────────────────────────┐   │
│  │   RAG Retriever       │◄──│   Suggestion Engine      │   │
│  │   • BGE-M3 embed      │   │   • Prompt template      │   │
│  │   • Chroma query      │──▶│   • DictaLM via Ollama   │   │
│  │   • Top-K + rerank    │   │   • Streaming tokens     │   │
│  └───────────┬───────────┘   └───────────┬──────────────┘   │
│              │                           │                 │
│              └──────┬────────────────────┘                 │
│                     │ suggestion + citations               │
│                     ▼                                       │
│         push to UI WebSocket                                │
│                                                             │
│  ┌─────────────────────┐   ┌──────────────────────────┐     │
│  │ KB Ingest Pipeline  │──▶│ ChromaDB (persistent)    │     │
│  │ • PDF/MD/TXT parse  │   │ • Collection per-install │     │
│  │ • Chunk + embed     │   └──────────────────────────┘     │
│  └─────────────────────┘                                    │
└─────────────────────────────────────────────────────────────┘
```

## Components

### 1. Frontend (Browser Sidebar)
- **Stack:** React + Vite + TypeScript, TailwindCSS
- **Responsibilities:** mic capture, live transcript render, suggestion render with citations, KB upload form, manual record toggle
- **State:** Minimal — transcript log, suggestion queue, KB status. Zustand or plain React context.
- **Transport:** Two WebSockets — one binary (audio out), one JSON (UI events in).

### 2. Backend Orchestrator (FastAPI)
- **Stack:** Python 3.11+, FastAPI, uvicorn, Pipecat (optional for pipeline)
- **Responsibilities:** WebSocket servers, pipeline wiring, lifecycle of STT/LLM/RAG sessions
- **Async model:** asyncio end-to-end; streaming all the way through

### 3. STT Service
- **Model:** `ivrit-ai/whisper-large-v3-turbo-ct2` via faster-whisper
- **Streaming wrapper:** WhisperLive or custom chunking (1-3s windows)
- **VAD:** Silero VAD for endpointing
- **Output:** Partial + final transcript events with timestamps

### 4. LLM Service
- **Model:** DictaLM 3.0 (12B on 32GB Mac, 1.7B on 16GB Mac)
- **Runtime:** Ollama with Metal acceleration
- **API:** OpenAI-compatible /chat/completions with streaming
- **Fallback:** Qwen 2.5 7B Instruct

### 5. RAG Service
- **Embeddings:** BGE-M3 via Ollama (dense retrieval first, reranking deferred)
- **Vector DB:** ChromaDB with persistent local storage
- **Ingest:** PDF/MD/TXT → chunking (500 tokens, 50 overlap) → embed → store
- **Query:** top-K=5 from last utterance, inject into suggestion prompt

### 6. Suggestion Engine
- **Prompt template:** Hebrew system prompt, role framing, retrieved context, last N turns of transcript, instruction to produce 1-3 short suggested replies with confidence
- **Output parsing:** Expect structured JSON with `suggestions[]` (text, confidence, citations)
- **Streaming:** Token-by-token to UI as soon as LLM starts producing

## Data Flow (hot path)

1. Browser captures mic audio → PCM frames over WebSocket A
2. Backend accumulates frames → Silero VAD detects speech chunks
3. Chunks → faster-whisper → partial transcript pushed to WebSocket B
4. On utterance-final: text → BGE-M3 → Chroma query → top-K chunks
5. Top-K + recent transcript → DictaLM prompt → streaming tokens
6. Parsed suggestion JSON → pushed to WebSocket B
7. Frontend renders suggestion cards with citation chips

**Latency budget:** VAD (50ms) + STT (500ms) + RAG (100ms) + LLM TTFT (400ms) + UI render (50ms) = ~1.1s target. 2s hard ceiling.

## Build order (phase sequencing implication)

1. **Foundation** — repo scaffold, Docker Compose, Python backend skeleton, frontend scaffold
2. **STT path** — STT service running standalone with a CLI test harness (no UI yet)
3. **LLM path** — Ollama + DictaLM running, simple prompt test
4. **RAG path** — KB ingest + retrieval working standalone
5. **Backend integration** — wire STT → RAG → LLM → WebSocket
6. **Frontend** — mic capture → transcript render → suggestion render
7. **Polish + demo** — prompt tuning, latency optimization, Docker Compose one-liner, README, end-to-end Hebrew demo

Phases 2-4 can run in parallel after Phase 1.

## Key architectural constraints

- **Streaming all the way through.** No component may buffer a full utterance before passing to the next stage. Pipecat's frame-based model enforces this naturally.
- **Single-process backend is fine for v1.** No microservices. No message queue. Just asyncio + Python.
- **Model files outside the Docker image.** Volumes mount `~/.receptra/models/` so images stay small and models survive container rebuilds.
- **No internet at runtime.** All models pre-downloaded. The hot path never hits the network.
- **Hebrew-specific text handling.** RTL rendering in the UI, bidi-aware transcript diffing, Hebrew-aware tokenization in chunker.
