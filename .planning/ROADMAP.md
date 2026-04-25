# Receptra — Milestone 1 Roadmap

*Hebrew-first, local-only, live agent co-pilot MVP. Exit criterion: live Hebrew demo on reference Apple Silicon (M2+) hardware.*

**Granularity:** standard (5-8 phases)
**Parallelization:** Phases 2, 3, 4 (STT / LLM / RAG) can execute in parallel after Phase 1 lands.
**Coverage:** 42/42 v1 REQ-IDs mapped.

## Phases

- [x] **Phase 1: Foundation** - Repo scaffold, Docker Compose on arm64, model download flow, healthchecks, CI, licensing
- [ ] **Phase 2: Hebrew Streaming STT** - faster-whisper + ivrit.ai turbo + Silero VAD streaming over WebSocket
- [ ] **Phase 3: Hebrew Suggestion LLM** - DictaLM 3.0 via Ollama (Qwen 2.5 fallback) producing grounded structured suggestions
- [ ] **Phase 4: Hebrew RAG Knowledge Base** - BGE-M3 + ChromaDB with Hebrew-aware chunking, ingest, and retrieval
- [ ] **Phase 5: Hot-Path Integration** - Wire STT → RAG → LLM → WebSocket with end-to-end latency instrumentation and audit log
- [ ] **Phase 6: Browser Sidebar Frontend** - React+Vite RTL Hebrew sidebar: mic capture, live transcript, suggestion cards, KB upload, i18n, a11y
- [ ] **Phase 7: Polish & Demo** - Latency tuning, prompt eval, Hebrew README, accessibility pass, public GitHub launch, recorded live demo

## Phase Details

### Phase 1: Foundation
**Goal**: A contributor can clone the repo and bring up a healthy (empty) arm64 stack with all models downloaded via a single documented flow.
**Depends on**: Nothing (first phase)
**Requirements**: FND-01, FND-02, FND-03, FND-04, FND-05, FND-06
**Success Criteria** (what must be TRUE):
  1. `docker compose up` on a fresh Apple Silicon Mac starts backend + frontend containers and both report healthy (backend `/healthz` 200, frontend sidebar page reachable).
  2. A separate `make setup` / model-download step fetches ivrit.ai Whisper, DictaLM (or Qwen fallback), and BGE-M3 into `~/.receptra/models/` with visible progress and survives container rebuilds.
  3. A fresh clone passes CI: lint, type-check, and a dependency license allowlist check block any GPL/AGPL/research-only deps.
  4. Repo root contains Apache 2.0 LICENSE, bilingual (EN + HE) README, and CONTRIBUTING.md.
**Skills**: none required (foundation is stack-agnostic; Hebrew copy handled in Phase 7).
**Pitfalls addressed**: #6 (arm64 wheels), #12 (model footprint split from image), #15 (license creep).
**Plans**: 6 plans
- [x] 01-01-PLAN.md — Repo root files: LICENSE, bilingual READMEs, CONTRIBUTING, .gitignore, .dockerignore, .env.example, knowledge/ + docs/ skeletons (FND-05)
- [x] 01-02-PLAN.md — Backend scaffold: Python 3.12 + uv + FastAPI + pydantic-settings + /healthz + Wave-0 pytest smoke (FND-01 backend half, FND-04 backend half)
- [x] 01-03-PLAN.md — Frontend scaffold: Vite 6 + React 19 + TS + Tailwind v4, RTL index.html, empty Receptra sidebar, /api + /ws dev proxy (FND-01, FND-04)
- [x] 01-04-PLAN.md — Docker Compose (arm64): chromadb + backend + frontend with healthcheck-gated chain; Ollama intentionally on host per OPEN-1 (FND-02)
- [x] 01-05-PLAN.md — Makefile + model download: hf CLI for Whisper + DictaLM GGUF + BGE-M3; DictaLM Modelfile + Qwen fallback; license-check wrapper (FND-03)
- [x] 01-06-PLAN.md — CI: ubuntu-latest lint + typecheck + test + compose-config + license allowlist; manual negative-gate regression workflow (FND-06)

### Phase 2: Hebrew Streaming STT
**Goal**: A headless test harness can stream Hebrew PCM audio in and receive live partial + final Hebrew transcripts with measured latency and WER.
**Depends on**: Phase 1
**Parallel with**: Phase 3, Phase 4
**Requirements**: STT-01, STT-02, STT-03, STT-04, STT-05, STT-06
**Success Criteria** (what must be TRUE):
  1. Backend loads `ivrit-ai/whisper-large-v3-turbo-ct2` via faster-whisper once at startup and accepts a WebSocket PCM stream.
  2. Silero VAD correctly segments speech, emitting partial Hebrew transcripts within ~1s of speech onset and a final transcript on end-of-speech.
  3. WER is measured and logged against a seeded 30-sample Hebrew audio fixture; baseline number is recorded in the phase transition doc.
  4. Per-request STT latency (speech-end → final transcript) is instrumented and written to the local log.
**Skills**: none required (model-level; Hebrew handling is inside the upstream model).
**Pitfalls addressed**: #1 (Hebrew WER on real audio), #4 (latency instrumentation at stage boundary).
**Plans**: 6 plans
- [ ] 02-01-PLAN.md — Wave-0 spike: pin deps (faster-whisper + silero-vad + jiwer + loguru), verify license allowlist, measure M2 int8 latency, lock partial cadence
- [x] 02-02-PLAN.md — FastAPI lifespan refactor + Whisper singleton on app.state + stt/engine.py Hebrew-locked transcribe wrapper (STT-01)
- [ ] 02-03-PLAN.md — Per-connection Silero VAD wrapper: 512-sample window + int16 LE → float32 + state isolation per connection (STT-02)
- [ ] 02-04-PLAN.md — /ws/stt WebSocket endpoint: pydantic event schema + VAD-gated re-transcribe loop + asyncio.to_thread transcribe (STT-03, STT-04)
- [ ] 02-05-PLAN.md — Hebrew WER eval harness: jiwer + NFC/niqqud normalisation + 30 Common Voice he-25.0 fixtures + eval CLI + regression test (STT-05)
- [ ] 02-06-PLAN.md — Latency instrumentation + SQLite stt_utterances stub + PII redaction + chaos disconnect test + docs/stt.md + docker-compose data volume (STT-06)

### Phase 3: Hebrew Suggestion LLM
**Goal**: A CLI harness can feed `(transcript, retrieved_context)` into the local LLM and receive grounded, structured Hebrew suggestions with TTFT measured.
**Depends on**: Phase 1
**Parallel with**: Phase 2, Phase 4
**Requirements**: LLM-01, LLM-02, LLM-03, LLM-04, LLM-05, LLM-06
**Success Criteria** (what must be TRUE):
  1. Ollama serves DictaLM 3.0 locally with the correct chat template (or Qwen 2.5 7B fallback, decision logged) and responds to Hebrew prompts in Hebrew.
  2. The suggestion engine emits valid structured JSON (`suggestions[]` with text, confidence, citation_ids) parseable by the backend.
  3. On empty or insufficient retrieved context, the model reliably outputs `"אין לי מספיק מידע"` instead of fabricating business facts.
  4. Time-to-first-token is instrumented and logged; the CLI harness runs end-to-end without any STT dependency.
**Skills**: none required at this phase (Hebrew NLP is prompt-level; tuning eval lives in Phase 7).
**Pitfalls addressed**: #2 (DictaLM deployment), #3 (memory pressure — Q4 quantization verified), #5 (grounding), #9 (chat template).
**Plans**: TBD

### Phase 4: Hebrew RAG Knowledge Base
**Goal**: A user can POST Hebrew `.md`/`.txt` docs to an ingest endpoint, have them chunked Hebrew-aware, embedded, persisted, and retrieved with cited source metadata.
**Depends on**: Phase 1
**Parallel with**: Phase 2, Phase 3
**Requirements**: RAG-01, RAG-02, RAG-03, RAG-04, RAG-05, RAG-06
**Success Criteria** (what must be TRUE):
  1. BGE-M3 via Ollama produces embeddings for Hebrew text and ChromaDB persists them across container restarts on a mounted volume.
  2. Ingest pipeline chunks Hebrew docs using sentence-aware segmentation (from `hebrew-nlp-toolkit` skill) without splitting mid-word or mid-sentence.
  3. REST ingest endpoint accepts `.md`/`.txt`, reports indexing status, and the retrieval endpoint returns top-K chunks with filename + offset metadata.
  4. Recall@5 is measured on a seeded Hebrew KB with 10 adversarial questions and recorded as a baseline.
**Skills**: `hebrew-nlp-toolkit` (chunking + tokenization), `hebrew-document-generator` (seed KB fixtures for eval).
**Pitfalls addressed**: #8 (Hebrew chunking), #13 (PDF flakiness — scope limited to md/txt).
**Plans**: TBD

### Phase 5: Hot-Path Integration
**Goal**: A headless end-to-end run (no frontend) takes a canned Hebrew audio fixture and produces a grounded streaming suggestion inside the latency budget, with full audit trail.
**Depends on**: Phase 2, Phase 3, Phase 4
**Requirements**: INT-01, INT-02, INT-03, INT-04, INT-05
**Success Criteria** (what must be TRUE):
  1. A single async pipeline streams audio → VAD → STT → RAG → LLM → UI WebSocket with no full-utterance buffering between stages.
  2. On every STT final-utterance event, the backend automatically runs retrieval and streams LLM suggestion tokens over the UI WebSocket.
  3. A CI smoke test asserts p95 end-to-end latency (speech-end → first suggestion token) <3s on a canned Hebrew audio fixture.
  4. Pipeline degrades gracefully for: empty KB, model-load failure, and WebSocket disconnect mid-utterance — each with a tested code path.
  5. All pipeline events are written to a local SQLite audit log with zero network egress.
**Skills**: none required at this phase (integration is plumbing; Hebrew content is already handled upstream).
**Pitfalls addressed**: #4 (latency cascade — per-stage budgets), #5 (grounding verified in pipeline), #14 (local-only telemetry).
**Plans**: TBD

### Phase 6: Browser Sidebar Frontend
**Goal**: An agent opens the browser sidebar, clicks Start, speaks Hebrew, and sees live RTL transcripts plus streaming grounded suggestion cards with citations — all backed by the Phase 5 hot path.
**Depends on**: Phase 5
**Requirements**: FE-01, FE-02, FE-03, FE-04, FE-05, FE-06, FE-07, FE-08
**Success Criteria** (what must be TRUE):
  1. React+Vite+TS sidebar renders an RTL-first Hebrew layout using `hebrew-tailwind-preset`, with correct bidi rendering of mixed Hebrew/English per `hebrew-rtl-best-practices`.
  2. Clicking Start triggers `getUserMedia`, streams PCM over WebSocket, and shows live partial + final Hebrew transcripts in RTL; the app never auto-listens on page load.
  3. Suggestion cards render streaming LLM tokens and display clickable citation chips that open the source KB snippet.
  4. KB upload form accepts `.md`/`.txt`, POSTs to the ingest endpoint, and surfaces indexing status feedback.
  5. UI is fully localized via `hebrew-i18n` (Hebrew default, English fallback) and keyboard-accessible against the Israeli Accessibility Regulations baseline.
**Skills**: `hebrew-tailwind-preset`, `hebrew-rtl-best-practices`, `hebrew-i18n`, `israeli-accessibility-compliance` (baseline scan; formal pass in Phase 7).
**Pitfalls addressed**: #7 (RTL/bidi bugs), #10 (mic permissions + HTTPS guidance), #11 (clear co-pilot framing in UI copy).
**Plans**: TBD
**UI hint**: yes

### Phase 7: Polish & Demo
**Goal**: A recorded live Hebrew demo on reference hardware meets the <2s p95 latency budget, the repo is public with a polished bilingual README, and Milestone 1 exit criterion is signed off.
**Depends on**: Phase 6
**Requirements**: DEMO-01, DEMO-02, DEMO-03, DEMO-04, DEMO-05
**Success Criteria** (what must be TRUE):
  1. On reference hardware (M2 16GB or M2 Pro 32GB), p95 end-to-end latency (speech-end → suggestion token on screen) measures <2s on a repeatable fixture.
  2. Suggestion prompt is tuned against a 20-example Hebrew eval set; accept-rate is reviewed and documented by a Hebrew speaker.
  3. Bilingual `README.md` (EN + HE) ships with install instructions, architecture diagram, and an embedded demo video/GIF.
  4. A recorded end-to-end demo shows: open browser → Start → speak Hebrew → live transcript → grounded suggestion with citation, verified running fully offline (airplane mode).
  5. Repo is published publicly on GitHub under Apache 2.0 with issue templates, a public roadmap section, and a full Israeli accessibility compliance pass.
**Skills**: `hebrew-content-writer` (README, landing copy, error messages), `israeli-accessibility-compliance` (formal pass), `hebrew-tailwind-preset` / `hebrew-rtl-best-practices` (final polish).
**Pitfalls addressed**: #4 (final latency tuning), #5 (prompt eval), #10 (HTTPS docs), #11 (clear co-pilot framing), #14 (local telemetry surfaced).
**Plans**: TBD
**UI hint**: yes

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 6/6 | Complete | 2026-04-24 |
| 2. Hebrew Streaming STT | 1/6 | In progress | - |
| 3. Hebrew Suggestion LLM | 0/0 | Not started | - |
| 4. Hebrew RAG Knowledge Base | 0/0 | Not started | - |
| 5. Hot-Path Integration | 0/0 | Not started | - |
| 6. Browser Sidebar Frontend | 0/0 | Not started | - |
| 7. Polish & Demo | 0/0 | Not started | - |

## Coverage Map

| Category | Requirements | Phase |
|----------|--------------|-------|
| Foundation | FND-01, FND-02, FND-03, FND-04, FND-05, FND-06 | Phase 1 |
| STT | STT-01, STT-02, STT-03, STT-04, STT-05, STT-06 | Phase 2 |
| LLM | LLM-01, LLM-02, LLM-03, LLM-04, LLM-05, LLM-06 | Phase 3 |
| RAG | RAG-01, RAG-02, RAG-03, RAG-04, RAG-05, RAG-06 | Phase 4 |
| Integration | INT-01, INT-02, INT-03, INT-04, INT-05 | Phase 5 |
| Frontend | FE-01, FE-02, FE-03, FE-04, FE-05, FE-06, FE-07, FE-08 | Phase 6 |
| Demo | DEMO-01, DEMO-02, DEMO-03, DEMO-04, DEMO-05 | Phase 7 |

**Total mapped: 42/42 v1 REQ-IDs. No orphans. No duplicates.**
