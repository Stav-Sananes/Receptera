# Research Summary — Receptra V1

*Synthesized from user-provided deep research + PROJECT.md decisions. This is the canonical briefing for roadmap creation.*

## Top insights

1. **Hebrew-first is the moat.** No open-source competitor has a production Hebrew voice AI pipeline. ivrit.ai (STT) + DictaLM 3.0 (LLM) are the only permissively-licensed, production-quality Hebrew building blocks. Every commercial leader (Vapi, Retell, Cresta) is English-centric and cloud-dependent — we win by being Hebrew-native and local-first.

2. **Co-pilot first is strategically right.** No TTS needed (which is good, because no production-quality Hebrew OSS TTS exists). Lower enterprise adoption barrier. Generates training data for later autonomous mode. Every major player in the space (Cresta, Observe.AI, Uniphore, Balto) started here.

3. **Apple Silicon is viable.** faster-whisper + Ollama with Metal on M2 16GB can realistically hit <2s end-to-end. 32GB enables the 12B DictaLM. The reference hardware is achievable for solo devs and SMB owners without a GPU.

4. **Streaming is non-negotiable.** The latency budget collapses if any stage buffers. Pipecat's frame architecture is designed for this, though we may be able to do it with plain asyncio + WebSockets given our simpler scope.

5. **"WordPress of voice AI" means UX, not framework.** Pipecat/LiveKit exist as developer tools. The gap is a product a non-technical SMB owner can deploy. Our differentiation is the install experience, not the underlying pipeline.

## Critical risks to design around

- Hebrew STT accuracy on real-world SMB audio (accents, noise) — validate early.
- DictaLM 3.0 deployment path via Ollama — verify day 1 it actually works.
- Memory pressure on 16GB Macs with STT + LLM + browser + OS — budget carefully.
- Latency cascade — instrument every stage with budgets from the start.
- Hallucinated business facts — strict RAG grounding + citations + eval harness.

## Stack (locked for v1)

- **STT:** faster-whisper + `ivrit-ai/whisper-large-v3-turbo-ct2` + Silero VAD
- **LLM:** DictaLM 3.0 via Ollama (Qwen 2.5 7B fallback)
- **Embeddings:** BGE-M3 via Ollama
- **Vector DB:** ChromaDB (persistent local)
- **Pipeline:** Pipecat OR plain asyncio (decide in Phase 1 spike)
- **Backend:** Python 3.11+ FastAPI
- **Frontend:** React + Vite + TypeScript + TailwindCSS
- **Deploy:** Docker Compose targeting arm64

## Scope (locked for v1)

**IN:** Live Hebrew transcription, reply suggestions with RAG-grounded citations, KB ingestion UI, browser sidebar, one-command Docker Compose install, Apple Silicon M2+ reference hardware, OSS repo with README/license/contribute guide.

**OUT:** TTS, autonomous voice, SIP/telephony, vertical templates, hosted SaaS, English parity, CUDA optimization, CRM integrations, sentiment/compliance, multi-tenant, mobile.

## Build sequence (informs roadmap)

1. **Foundation** — repo, Docker Compose, backend skeleton, frontend skeleton, model download flow
2. **STT** — streaming Hebrew transcription working end-to-end in isolation
3. **LLM** — DictaLM via Ollama producing Hebrew suggestions from a prompt
4. **RAG** — KB ingest + retrieval working in isolation
5. **Integration** — wire STT → RAG → LLM → WebSocket; end-to-end headless pipeline
6. **Frontend** — browser sidebar consuming live WebSocket streams
7. **Polish + demo** — latency tuning, prompt tuning, README, end-to-end Hebrew demo on reference hardware

Phases 2-4 can run in parallel after Phase 1 lands.

## Exit criterion for Milestone 1

A live Hebrew demo runs end-to-end on a reference Apple Silicon Mac:
- User opens the sidebar in a browser
- Clicks start, speaks Hebrew into the mic
- Sees live transcription appear within ~1s
- Sees a grounded suggestion with a citation from the uploaded KB within ~2s of finishing their sentence
- All running locally with no internet connection
