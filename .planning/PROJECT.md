# Receptra

## What This Is

Receptra is an open-source, self-hosted Hebrew-first AI voice platform for small businesses — the "WordPress of voice AI." V1 ships as a **live agent co-pilot**: a browser-based sidebar that listens to a human agent's phone call, streams Hebrew transcription, and surfaces suggested replies plus RAG answers from the business knowledge base in real time. The full autonomous voice receptionist comes later on the same foundation.

## Core Value

**A human agent taking a Hebrew call on a Mac gets useful, grounded suggestions in under two seconds — running entirely on their own machine with no cloud dependency.**

If everything else fails, this must work. Hebrew + local + live-latency is the moat.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Live Hebrew speech-to-text streaming from browser mic with <2s caption latency
- [ ] Local LLM suggestion engine (DictaLM 3.0 or Qwen 2.5) producing grounded reply suggestions
- [ ] RAG over a user-supplied Hebrew knowledge base (docs, FAQs, policies) with BGE-M3 + local vector DB
- [ ] Browser sidebar UI showing live transcript, suggestions, and cited knowledge snippets
- [ ] One-command Docker Compose self-host deployment targeting Apple Silicon (M2+)
- [ ] End-to-end live Hebrew demo runnable on reference M2+ hardware (Milestone 1 exit criterion)
- [ ] Public OSS repo with README, license, contribution guide

### Out of Scope (for Milestone 1)

- **Text-to-speech / autonomous voice bot** — co-pilot first; no TTS until M2+ validation lands
- **Telephony / SIP integration** — browser mic only in v1; phone bridge is a later milestone
- **Vertical-specific templates (dental, legal, etc.)** — generic receptionist only; verticalization waits for user signal
- **Hosted SaaS / managed cloud tier** — OSS self-host first; monetization path comes after community traction
- **English-first or multilingual parity** — Hebrew is the day-1 moat; English is a follow-up
- **Windows/Linux GPU optimization** — Apple Silicon is the reference floor; CUDA support is a later concern
- **CRM integrations, sentiment, compliance flags** — full assist suite deferred; v1 is suggestions + RAG only
- **Enterprise features (SSO, HIPAA, multi-tenant)** — OSS community tier only

## Context

**Market:** Voice AI market is expanding from $2.4B (2024) to a projected $47.5B (2034). No open-source project has captured the no-code SMB niche. Commercial players (Vapi, Retell, Synthflow, Bland) target developers or enterprise — none are Hebrew-first. Israel has ~580,000 SMBs with no dominant Hebrew AI receptionist platform, making it a defensible beachhead.

**Strategic framing:** Research strongly recommended starting with agent co-pilot rather than full autonomous voice bot. Rationale: (1) no TTS or turn-taking complexity, (2) human catches AI errors so enterprise adoption barrier is lower, (3) every commercial leader (Cresta, Observe.AI, Uniphore, Balto) started here before adding autonomy, (4) co-pilot data becomes training signal for later autonomous mode.

**Technical environment:**
- **STT:** faster-whisper with ivrit.ai fine-tuned Whisper models (Hebrew gold standard, ~22,000 hours of training data, Apache 2.0).
- **LLM:** DictaLM 3.0 (Hebrew-optimized, ~100B Hebrew tokens, native tool-calling) as primary, Qwen 2.5 7B as fallback. Served via Ollama or llama.cpp with Metal acceleration on Apple Silicon.
- **Embeddings + RAG:** BGE-M3 embeddings + ChromaDB (dev) or Qdrant (production).
- **Pipeline:** Pipecat frame-based streaming for STT→LLM→UI. No TTS in v1.
- **Transport:** WebRTC (browser mic) via LiveKit or bare WebRTC; no SIP/telephony in v1.
- **Frontend:** Browser sidebar (exact framework TBD — React + Vite likely).

**Available Hebrew tooling (via `skills-il`):** The following Claude skills are installed globally and should be invoked by the relevant phases:
- `hebrew-rtl-best-practices` — RTL layout, bidi rendering, mixed-script handling (Frontend phase)
- `hebrew-tailwind-preset` — Tailwind config with Hebrew fonts, RTL utilities (Frontend phase)
- `hebrew-i18n` — i18n scaffolding, locale files, string extraction (Frontend phase)
- `hebrew-nlp-toolkit` — Hebrew-aware tokenization, chunking, normalization (RAG phase — directly addresses pitfall #8)
- `israeli-accessibility-compliance` — IL Accessibility Regulations checklist (Polish phase)
- `hebrew-content-writer` — Hebrew README, landing copy, error messages (Polish phase)
- `hebrew-document-generator` — test KB docs for RAG evaluation (RAG phase)

**Hebrew TTS gap:** No production-quality open-source Hebrew TTS exists today. This validates the decision to skip TTS in v1 and start with a co-pilot that only needs STT + LLM. Edge-TTS (free Microsoft wrapper) is the fallback for the eventual autonomous mode.

**Monetization roadmap (informational, not v1 scope):** Open-core playbook validated by n8n ($40M ARR), Supabase ($70M ARR), PostHog ($920M valuation). Free self-hosted OSS → hosted cloud tier → business/agency tier → enterprise. Not building any of this in Milestone 1.

## Constraints

- **Language:** Hebrew is the day-1 target. Every v1 choice must work in Hebrew before any English optimization.
- **Hardware floor:** Apple Silicon M2 or newer with 16GB+ unified memory. No CUDA requirement for v1. CPU-only is explicitly not supported (latency budget blown).
- **Licensing:** Full stack must be permissively licensed (Apache 2.0, MIT, BSD) or explicitly free-for-commercial (Edge-TTS). No GPL or research-only licenses in v1 dependencies.
- **Privacy:** Zero cloud dependency for the core loop — audio, transcripts, and LLM inference must run locally. A user can air-gap the machine and v1 still works.
- **Latency:** End-to-end speech → suggestion on screen target <2s (Cresta achieves <200ms; our bar is looser because we're local-first on consumer hardware).
- **Deployment:** One command (`docker compose up` or equivalent) must bring the whole stack online on a fresh Mac.
- **Distribution:** OSS self-host first. No hosted SaaS in Milestone 1.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Start with agent co-pilot (not autonomous voice bot) | Lower technical scope (no TTS, no turn-taking), lower enterprise adoption barrier, proven trajectory of every commercial leader, generates training data for later autonomous mode | — Pending |
| Hebrew-first on day 1 | Strongest open-source moat — no end-to-end Hebrew voice AI pipeline exists. 580k Israeli SMBs with no dominant player. ivrit.ai + DictaLM make it technically viable. | — Pending |
| Generic receptionist (no vertical lock-in in v1) | Avoid premature specialization; let early users surface which vertical pulls first | — Pending |
| OSS self-host first, hosted SaaS later | Community moat before monetization. Follows n8n/Supabase/PostHog playbook. | — Pending |
| Apple Silicon M2+ as hardware floor | User's primary dev environment is Mac; Metal-accelerated local inference is viable for STT + 7B LLM; sidesteps CUDA complexity | — Pending |
| Browser mic capture (not SIP telephony) in v1 | Eliminates Asterisk/LiveKit-SIP setup from the first milestone; agents can wear a headset and route existing calls through the browser | — Pending |
| Live suggestions + RAG (not transcript-only, not full assist suite) | Real co-pilot value without the scope sprawl of sentiment/compliance/CRM features | — Pending |
| DictaLM 3.0 as primary LLM, Qwen 2.5 7B as fallback | DictaLM is the only Hebrew-optimized model with native tool-calling; Qwen is the best general-purpose fallback for function-calling workloads | — Pending |
| Milestone 1 exit = live Hebrew demo on reference M2+ hardware | Internal quality bar before going public. GitHub metrics and external users come in later milestones. | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-15 after initialization*
