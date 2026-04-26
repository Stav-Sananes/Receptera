# Receptra — v1 Requirements

*Milestone 1: Hebrew Co-pilot MVP. Exit criterion: live Hebrew demo end-to-end on reference Apple Silicon hardware.*

## v1 Requirements

### Foundation

- [x] **FND-01**: Project repository scaffolded with Python backend, React+Vite frontend, and docs directory (backend complete 01-02; frontend complete 01-03)
- [x] **FND-02
**: Docker Compose stack (arm64-compatible) starts the full system with a single command
- [x] **FND-03**: Model download step (separate from `docker compose up`) fetches ivrit.ai Whisper, DictaLM, and BGE-M3 to a mounted volume with progress output (complete 01-05)
- [x] **FND-04**: Backend and frontend scaffolds produce a healthy `/healthz` endpoint and a reachable empty sidebar page (backend `/healthz` complete 01-02; frontend sidebar complete 01-03)
- [x] **FND-05**: Apache 2.0 LICENSE, README.md (English + Hebrew), and CONTRIBUTING.md exist at repo root
- [x] **FND-06**: CI pipeline runs lint + type-check + license allowlist check on every commit (complete 01-06)

### STT (Hebrew Streaming Speech-to-Text)

- [x] **STT-01**: Backend runs `faster-whisper` with the `ivrit-ai/whisper-large-v3-turbo-ct2` model, loaded once at startup (complete 02-02)
- [x] **STT-02**: Silero VAD identifies speech chunks from an incoming PCM audio stream (complete 02-03)
- [x] **STT-03**: Backend exposes a WebSocket endpoint that accepts binary PCM frames and emits partial Hebrew transcripts within ~1s of speech onset (complete 02-04)
- [x] **STT-04**: Final-utterance transcript events are emitted when VAD detects end-of-speech (complete 02-04)
- [x] **STT-05
**: STT accuracy is verified against a seeded 30-sample Hebrew audio test set with WER measured and logged
- [x] **STT-06
**: STT latency (time from speech end to final transcript) is instrumented and logged per request

### LLM (Hebrew Suggestion Engine)

- [x] **LLM-01
**: Ollama runs locally with DictaLM 3.0 as the primary Hebrew model (Qwen 2.5 7B as fallback if DictaLM deployment is blocked)
- [ ] **LLM-02**: Backend exposes an internal suggestion-engine interface that accepts (transcript, retrieved_context) and streams structured reply suggestions
- [x] **LLM-03
**: Suggestion prompt enforces grounding: model must only use retrieved context and must say "אין לי מספיק מידע" when context is insufficient
- [x] **LLM-04
**: LLM output is parsed into structured JSON with `suggestions[]` (text, confidence, citation_ids)
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

*Maps each REQ-ID to its phase. 42/42 v1 requirements mapped. No orphans.*

| REQ-ID | Phase | Status |
|--------|-------|--------|
| FND-01 | Phase 1: Foundation | Complete (backend 01-02; frontend 01-03) |
| FND-02 | Phase 1: Foundation | Complete (01-04) |
| FND-03 | Phase 1: Foundation | Complete (01-05) |
| FND-04 | Phase 1: Foundation | Complete (backend /healthz 01-02; frontend sidebar 01-03) |
| FND-05 | Phase 1: Foundation | Complete (01-01) |
| FND-06 | Phase 1: Foundation | Complete (01-06) |
| STT-01 | Phase 2: Hebrew Streaming STT | Complete (02-02) |
| STT-02 | Phase 2: Hebrew Streaming STT | Complete (02-03) |
| STT-03 | Phase 2: Hebrew Streaming STT | Complete (02-04) |
| STT-04 | Phase 2: Hebrew Streaming STT | Complete (02-04) |
| STT-05 | Phase 2: Hebrew Streaming STT | Complete (02-05) |
| STT-06 | Phase 2: Hebrew Streaming STT | Complete (02-06) |
| LLM-01 | Phase 3: Hebrew Suggestion LLM | Complete (03-01) |
| LLM-02 | Phase 3: Hebrew Suggestion LLM | Pending |
| LLM-03 | Phase 3: Hebrew Suggestion LLM | Complete (03-02 — schema + prompt level lock) |
| LLM-04 | Phase 3: Hebrew Suggestion LLM | Complete (03-02 — schema + prompt level lock) |
| LLM-05 | Phase 3: Hebrew Suggestion LLM | Pending |
| LLM-06 | Phase 3: Hebrew Suggestion LLM | Pending |
| RAG-01 | Phase 4: Hebrew RAG Knowledge Base | Pending |
| RAG-02 | Phase 4: Hebrew RAG Knowledge Base | Pending |
| RAG-03 | Phase 4: Hebrew RAG Knowledge Base | Pending |
| RAG-04 | Phase 4: Hebrew RAG Knowledge Base | Pending |
| RAG-05 | Phase 4: Hebrew RAG Knowledge Base | Pending |
| RAG-06 | Phase 4: Hebrew RAG Knowledge Base | Pending |
| INT-01 | Phase 5: Hot-Path Integration | Pending |
| INT-02 | Phase 5: Hot-Path Integration | Pending |
| INT-03 | Phase 5: Hot-Path Integration | Pending |
| INT-04 | Phase 5: Hot-Path Integration | Pending |
| INT-05 | Phase 5: Hot-Path Integration | Pending |
| FE-01 | Phase 6: Browser Sidebar Frontend | Pending |
| FE-02 | Phase 6: Browser Sidebar Frontend | Pending |
| FE-03 | Phase 6: Browser Sidebar Frontend | Pending |
| FE-04 | Phase 6: Browser Sidebar Frontend | Pending |
| FE-05 | Phase 6: Browser Sidebar Frontend | Pending |
| FE-06 | Phase 6: Browser Sidebar Frontend | Pending |
| FE-07 | Phase 6: Browser Sidebar Frontend | Pending |
| FE-08 | Phase 6: Browser Sidebar Frontend | Pending |
| DEMO-01 | Phase 7: Polish & Demo | Pending |
| DEMO-02 | Phase 7: Polish & Demo | Pending |
| DEMO-03 | Phase 7: Polish & Demo | Pending |
| DEMO-04 | Phase 7: Polish & Demo | Pending |
| DEMO-05 | Phase 7: Polish & Demo | Pending |
