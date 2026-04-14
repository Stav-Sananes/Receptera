# Receptra — v1 Requirements

*Milestone 1: Hebrew Co-pilot MVP. Exit criterion: live Hebrew demo end-to-end on reference Apple Silicon hardware.*

## v1 Requirements

### Foundation

- [ ] **FND-01**: Project repository scaffolded with Python backend, React+Vite frontend, and docs directory
- [ ] **FND-02**: Docker Compose stack (arm64-compatible) starts the full system with a single command
- [ ] **FND-03**: Model download step (separate from `docker compose up`) fetches ivrit.ai Whisper, DictaLM, and BGE-M3 to a mounted volume with progress output
- [ ] **FND-04**: Backend and frontend scaffolds produce a healthy `/healthz` endpoint and a reachable empty sidebar page
- [ ] **FND-05**: Apache 2.0 LICENSE, README.md (English + Hebrew), and CONTRIBUTING.md exist at repo root
- [ ] **FND-06**: CI pipeline runs lint + type-check + license allowlist check on every commit

### STT (Hebrew Streaming Speech-to-Text)

- [ ] **STT-01**: Backend runs `faster-whisper` with the `ivrit-ai/whisper-large-v3-turbo-ct2` model, loaded once at startup
- [ ] **STT-02**: Silero VAD identifies speech chunks from an incoming PCM audio stream
- [ ] **STT-03**: Backend exposes a WebSocket endpoint that accepts binary PCM frames and emits partial Hebrew transcripts within ~1s of speech onset
- [ ] **STT-04**: Final-utterance transcript events are emitted when VAD detects end-of-speech
- [ ] **STT-05**: STT accuracy is verified against a seeded 30-sample Hebrew audio test set with WER measured and logged
- [ ] **STT-06**: STT latency (time from speech end to final transcript) is instrumented and logged per request

### LLM (Hebrew Suggestion Engine)

- [ ] **LLM-01**: Ollama runs locally with DictaLM 3.0 as the primary Hebrew model (Qwen 2.5 7B as fallback if DictaLM deployment is blocked)
- [ ] **LLM-02**: Backend exposes an internal suggestion-engine interface that accepts (transcript, retrieved_context) and streams structured reply suggestions
- [ ] **LLM-03**: Suggestion prompt enforces grounding: model must only use retrieved context and must say "אין לי מספיק מידע" when context is insufficient
- [ ] **LLM-04**: LLM output is parsed into structured JSON with `suggestions[]` (text, confidence, citation_ids)
- [ ] **LLM-05**: Time-to-first-token is instrumented and logged per request
- [ ] **LLM-06**: Suggestion engine is testable via a CLI harness independent of the STT pipeline

### RAG (Knowledge Base Retrieval)

- [ ] **RAG-01**: BGE-M3 embeddings run via Ollama and produce vectors for Hebrew text
- [ ] **RAG-02**: ChromaDB persists embeddings to a mounted volume and survives container restarts
- [ ] **RAG-03**: KB ingest pipeline accepts `.md` and `.txt` files, uses Hebrew-aware sentence chunking (via `hebrew-nlp-toolkit` skill), embeds, and stores
- [ ] **RAG-04**: Retrieval endpoint returns top-K chunks with source metadata (filename, chunk offset) for a Hebrew query
- [ ] **RAG-05**: Retrieval quality is verified on a seeded Hebrew KB with 10 adversarial questions measuring recall@5
- [ ] **RAG-06**: Ingest is exposed via a REST endpoint the frontend can call

### Integration (Hot Path)

- [ ] **INT-01**: Backend wires STT → RAG → LLM → UI-WebSocket in a single async pipeline with no buffering between stages
- [ ] **INT-02**: On every final-utterance STT event, backend triggers retrieval and suggestion generation and streams tokens to the UI WebSocket
- [ ] **INT-03**: End-to-end latency (speech end → first suggestion token on screen) is instrumented; a CI smoke test asserts <3s p95 on a canned audio fixture
- [ ] **INT-04**: Pipeline gracefully handles: empty KB, model load failure, WebSocket disconnect mid-utterance
- [ ] **INT-05**: All pipeline events are logged to a local SQLite audit log (local-only, no phone-home)

### Frontend (Browser Sidebar)

- [ ] **FE-01**: React+Vite+TypeScript app renders a sidebar layout using `hebrew-tailwind-preset` with RTL-first styling
- [ ] **FE-02**: Browser captures microphone audio via `getUserMedia` and streams PCM frames over WebSocket to the backend
- [ ] **FE-03**: Manual Start/Stop recording toggle — the app never auto-listens on page load
- [ ] **FE-04**: Live transcript pane shows partial and final transcripts with RTL text rendering (per `hebrew-rtl-best-practices` skill)
- [ ] **FE-05**: Suggestion cards render streaming LLM tokens and display clickable citation chips showing the source KB snippet
- [ ] **FE-06**: KB upload form accepts `.md`/`.txt` files, POSTs to the ingest endpoint, and shows indexing status
- [ ] **FE-07**: UI strings are localized via `hebrew-i18n` skill scaffolding (Hebrew default, English fallback)
- [ ] **FE-08**: Sidebar is keyboard accessible and meets Israeli Accessibility Regulations baseline (per `israeli-accessibility-compliance` skill)

### Polish & Demo

- [ ] **DEMO-01**: Latency budget met on reference hardware: p95 end-to-end <2s on an Apple Silicon M2 (16GB) or M2 Pro (32GB)
- [ ] **DEMO-02**: Suggestion prompt is tuned against a 20-example eval set and accept-rate is measured (qualitative review by a Hebrew speaker)
- [ ] **DEMO-03**: `README.md` (English + Hebrew) includes install instructions, demo video/GIF, and architecture diagram
- [ ] **DEMO-04**: A recorded demo shows: open browser → click start → speak Hebrew → see live transcript → see grounded suggestion with citation, all offline
- [ ] **DEMO-05**: Repo is published publicly on GitHub with Apache 2.0 LICENSE, issue templates, and a public roadmap section

## v2 (Deferred — not in Milestone 1)

- Telephony / SIP bridge (Asterisk or LiveKit SIP)
- Text-to-speech / autonomous voice response
- Post-call summary generation
- Call analytics dashboard
- CRM integrations (HubSpot, Salesforce)
- Sentiment detection
- Compliance / PII flagging
- Multi-agent / team support
- English language parity
- Vertical-specific templates (dental, legal, salon)
- Hosted SaaS tier
- Windows/Linux CUDA optimization

## Out of Scope (explicit exclusions with reasoning)

- **Cloud LLM fallback** — violates "zero cloud dependency" core value
- **Multi-tenant auth / RBAC** — single-user SMB install is v1 scope
- **Mobile app** — browser-only in v1; mobile browser is best-effort
- **Custom voice cloning** — not needed without TTS
- **Real-time speaker diarization** — v1 assumes single-agent audio input
- **Enterprise features (SSO, SAML, HIPAA certification)** — community OSS tier only
- **Fine-tuning DictaLM on user transcripts** — out of scope; use as-is
- **Real-time translation** — Hebrew only in v1

## Traceability

*Populated by the roadmapper agent — maps each REQ-ID to a phase.*

| REQ-ID | Phase | Status |
|--------|-------|--------|
| (pending roadmap creation) | | |
