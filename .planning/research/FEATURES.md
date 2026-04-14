# FEATURES — Agent Co-pilot for SMBs (Hebrew-first)

*Source: user-provided research report on Cresta/Observe.AI/Uniphore/Balto + Receptra PROJECT.md scope.*

## Table Stakes (must have in v1 or the product is not useful)

| Feature | Why it's table stakes | Complexity |
|---|---|---|
| **Live Hebrew transcription** | Without it, nothing else works. Agent must see what the caller said. | High — streaming STT + Hebrew accuracy |
| **Live reply suggestions** | The "co-pilot" value prop. Without it, this is just a transcript tool. | High — streaming LLM + prompt engineering |
| **RAG over a knowledge base** | Suggestions must be grounded. Ungrounded LLM output will hallucinate business facts. | Medium — ingest, embed, retrieve |
| **Source citations on suggestions** | Agent needs to trust the suggestion enough to use it. Shows which KB doc it came from. | Low |
| **One-command local deployment** | "WordPress of voice AI" promise. Dentist cannot run a K8s cluster. | Medium |
| **Browser sidebar UI** | Co-pilot needs a live surface. Agent wears a headset, keeps browser tab open. | Medium |
| **Knowledge base ingestion UI** | Upload PDFs/docs, see them indexed. Without UI this is a dev tool, not a product. | Medium |
| **Manual start/stop recording control** | Privacy + agent control. Must not auto-listen. | Low |

## Differentiators (nobody else has these + meaningful)

| Feature | Why it differentiates | Complexity |
|---|---|---|
| **Hebrew out of the box** | No open-source competitor has production Hebrew. ivrit.ai models + DictaLM = unique stack. | High but already-solved by upstream |
| **100% local, air-gappable** | Vapi/Retell/Cresta are all cloud. Local = privacy story for legal/medical verticals. | Medium |
| **Runs on a Mac Mini** | No GPU server required. Consumer hardware floor. | Medium |
| **Open-source self-host** | No other no-code SMB voice AI is OSS. Community moat. | Low |
| **Docker Compose one-liner** | WordPress-style install experience. | Medium |
| **Suggestion confidence score** | Helps agent decide whether to use or ignore. | Low |

## Nice-to-have (future milestones, NOT v1)

- Post-call summary generation
- Call analytics dashboard (suggestion accept rate, latency, etc.)
- CRM write-back (HubSpot, Salesforce, etc.)
- Sentiment detection
- Compliance/PII flagging
- Multi-agent / team support
- Custom voice training data upload
- Fine-tuning the suggestion LLM on the business's past transcripts

## Anti-features (deliberately NOT building)

- **Autonomous voice response (TTS out)** — Deferred to post-v1 milestone. No Hebrew OSS TTS.
- **Telephony / SIP integration** — v1 is browser mic only. Asterisk/SIP is a later milestone.
- **Vertical templates (dental, legal, salon)** — Premature specialization. Wait for user pull.
- **Hosted SaaS tier** — OSS first. No multi-tenant code in v1.
- **English parity** — Hebrew-first is the moat. English is a follow-up milestone.
- **Windows/Linux CUDA support** — Apple Silicon is the reference floor.
- **Cloud LLM fallback** — Violates privacy constraint. Local or nothing.
- **Real-time sentiment / compliance** — Scope sprawl. Not v1.
- **Multi-user auth / RBAC** — Single-user dev/SMB install in v1.
- **Mobile app** — Browser only.

## Feature dependencies

```
Docker deploy ──┬──> Backend (FastAPI) ──> STT (faster-whisper)
                │                      └──> LLM (Ollama + DictaLM)
                │                      └──> RAG (BGE-M3 + Chroma)
                │
                └──> Frontend (React sidebar) ──> WebRTC mic capture
                                               └──> WebSocket to backend
                                               └──> Live transcript view
                                               └──> Suggestion view
                                               └──> KB upload UI
```

Build order implication: backend pipeline must work standalone (headless) before sidebar UI is wired in. KB ingestion can be built in parallel.
