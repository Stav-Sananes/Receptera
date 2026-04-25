# Phase 3: Hebrew Suggestion LLM — Research

**Researched:** 2026-04-25
**Domain:** Local LLM serving (Ollama + DictaLM 3.0), Hebrew prompt engineering, structured JSON output, streaming + TTFT instrumentation, CLI eval harness
**Confidence:** HIGH (Ollama Python API verified via Context7; DictaLM 3.0 chat template verified by direct fetch; JSON-schema-streaming caveat verified via upstream issue tracker)

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| LLM-01 | Ollama runs locally with DictaLM 3.0 primary; Qwen 2.5 7B fallback | §2 (Ollama runtime), §3 (DictaLM Modelfile), Phase 1 RESEARCH §2.2 already locked import flow |
| LLM-02 | Backend internal interface accepting `(transcript, retrieved_context)` → streams structured suggestions | §6 (Backend integration), §7 (CLI harness), Architectural Map |
| LLM-03 | Prompt enforces grounding; outputs `"אין לי מספיק מידע"` on insufficient context | §5 (Prompt template), §5.5 (Grounding patterns), §11 (Validation: grounding probe) |
| LLM-04 | Output parsed to structured JSON `suggestions[]` (text, confidence, citation_ids) | §3.5 (Streaming caveat), §4 (Pydantic schema), §6.2 (Parse + retry) |
| LLM-05 | TTFT instrumented + logged per request | §6.3 (TTFT pattern), §6.4 (SQLite stub), §11 (Validation contract) |
| LLM-06 | CLI harness exercises engine independent of STT | §7 (CLI harness spec) |
</phase_requirements>

## Summary

Phase 3 stands up a locally-served Hebrew LLM (DictaLM 3.0 via Ollama) behind an **internal Python interface** — `generate_suggestions(transcript, context_chunks)` returning an `AsyncGenerator[SuggestionEvent, None]` — that is the single dependency point Phase 4 (RAG) and Phase 5 (hot-path) integrate against. The phase deliberately ships **no public HTTP/WebSocket route**: the CLI harness (`scripts/eval_llm.py`) is the only external entry point, which keeps the suggestion engine testable, prompt-tunable, and reusable across the RAG and hot-path phases.

The single most consequential architectural finding: **Ollama's `format=<json-schema>` enforcement does NOT reliably hold under streaming with reasoning/thinking models** [VERIFIED: ollama/ollama issue #14440]. Streaming + structured outputs is officially supported but not strictly schema-validated mid-stream. We resolve this by adopting a **two-track output protocol**: stream raw token deltas to the UI for perceived-latency wins (TTFT < 500 ms target), then parse the assembled completion against the Pydantic schema at `done=true` — failure triggers one bounded retry with a stricter system prompt, then falls back to the canonical "אין לי מספיק מידע" suggestion. No Phase 5 UI consumer ever has to handle malformed JSON.

DictaLM 3.0 Nemotron 12B uses **ChatML** (`<|im_start|>` / `<|im_end|>`) with a custom-instructions-aware system slot — verified by fetching the model's `chat_template.jinja` directly. The existing `scripts/ollama/DictaLM3.Modelfile` correctly relies on Ollama's auto-detection of `tokenizer.chat_template` GGUF metadata; no manual `TEMPLATE` block is needed. Stale advice elsewhere on the web telling users to "use mistral-instruct template, no system prompt" applies to DictaLM **2.0** and must NOT be followed for 3.0.

**Primary recommendation:** Direct `ollama` Python client (>=0.6.1) using `AsyncClient`, with streaming for token deltas + JSON parse on completion, behind a thin `receptra.llm` package. No Pipecat in this phase (it is correctly deferred to Phase 5 per Phase 1 RESEARCH §3.5).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Ollama HTTP server (DictaLM serving) | Host (macOS, Metal) | — | Phase 1 OPEN-1 locked: in-Compose Ollama on Mac collapses to CPU; Metal demands host-native serving |
| `receptra.llm` Python package (engine + prompts + schema) | API / Backend (FastAPI process) | — | Same backend container that owns STT pipeline; no separate process |
| Streaming token chunk delivery | API / Backend → (Phase 5) Browser via WebSocket | — | Phase 3 publishes the AsyncGenerator; Phase 5 wires it to `/ws/agent` |
| JSON schema enforcement | API / Backend (post-stream parse) | — | Streaming + format=schema is unreliable upstream — final-completion parse is the contract |
| TTFT instrumentation | API / Backend (loguru + SQLite) | — | Co-located with stt_utterances stub from Plan 02-06 (same audit DB) |
| CLI harness | Build / Dev tooling (`scripts/eval_llm.py`) | — | Filesystem CLI; no service surface; runs against host Ollama directly |
| Prompt template + few-shot examples | Source-controlled module (`receptra.llm.prompts`) | — | Versioned with code; eval-friendly; Phase 7 prompt tuning consumes this |

## Findings

### 1. Ollama Python Client (>=0.6.1)

[VERIFIED: pypi.org/project/ollama, latest 0.6.1 released 2025-11-13, supports Python 3.8+]

**1.1 Sync vs async.** `ollama` ships `chat()` (sync), `Client(...).chat()` (sync, configurable host), and `AsyncClient(...).chat()` (async). FastAPI integration **must** use `AsyncClient` to avoid blocking the event loop — same lesson as Plan 02-04's `asyncio.to_thread(transcribe_hebrew, ...)` (Pitfall #5 in STT). [CITED: github.com/ollama/ollama-python README — "AsyncClient class for non-blocking operations particularly beneficial in web servers"]

**1.2 Streaming chat call shape:**

```python
from ollama import AsyncClient

client = AsyncClient(host=settings.ollama_host)  # http://host.docker.internal:11434

stream = await client.chat(
    model="dictalm3",
    messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_msg}],
    stream=True,
    options={"temperature": 0.0, "num_predict": 512, "num_ctx": 8192},
    # NOTE: format=<schema> is intentionally OMITTED while stream=True (see §3.5)
)
async for chunk in stream:
    delta = chunk["message"]["content"]  # str, may be empty
    done = chunk.get("done", False)
    # ...
```

[VERIFIED: Context7 /ollama/ollama-python README excerpt + docs.ollama.com/api/chat]

**1.3 Chunk shape:**

```json
{
  "model": "dictalm3",
  "created_at": "2026-04-25T...",
  "message": { "role": "assistant", "content": "<delta>" },
  "done": false
}
```

The final chunk carries `done: true` plus completion-level fields: `total_duration`, `load_duration`, `prompt_eval_count`, `prompt_eval_duration`, `eval_count`, `eval_duration` (nanoseconds). [VERIFIED: docs.ollama.com/api/chat 2026]

**1.4 TTFT measurement.** TTFT = `t_first_nonempty_chunk - t_request_sent`. Measured in Python with `time.perf_counter()` bracketing the `await client.chat(...)` call and the first iteration of `async for chunk in stream` where `chunk["message"]["content"]` is non-empty. The `prompt_eval_duration` field reported in the final chunk is informational (Ollama-internal prompt-eval phase) and is NOT a substitute for wall-clock TTFT — Phase 5 latency budget is wall-clock end-to-end.

**1.5 Custom host.** `AsyncClient(host="http://host.docker.internal:11434")` is the canonical way to point at host Ollama from inside the backend container. Phase 1 already locked this via `RECEPTRA_OLLAMA_HOST` in `Settings` — no new config needed. [VERIFIED: backend/src/receptra/config.py line 24]

### 2. Connecting from Backend Container

**2.1 Already wired.** `Settings.ollama_host` defaults to `http://host.docker.internal:11434`; `docker-compose.yml` already declares `extra_hosts: ["host.docker.internal:host-gateway"]` on the backend service (Plan 01-04). Phase 3 needs zero compose-level changes.

**2.2 Connection sanity probe.** Add a startup health probe that calls `await client.list()` and logs the available models. If `dictalm3` is missing AND `qwen2.5:7b` is missing, log an error and continue (suggestion engine returns `"אין לי מספיק מידע"` graceful-degraded responses; the backend `/healthz` stays green to keep STT functional). This honors INT-04 Phase 5's "model load failure" branch in the same code path. [Recommended pattern, not literal API quote]

**2.3 Connection timeout.** `AsyncClient(host=..., timeout=httpx.Timeout(30.0))` — Ollama's keep-alive load can take seconds on cold start (Phase 1 set `keep_alive: -1` in DictaLM3.Modelfile to pin weights, but warmup still costs ~5 s on first call). 30 s timeout is conservative enough for cold-start while bounded enough that a hung Ollama process doesn't wedge the WS hot path indefinitely.

### 3. DictaLM 3.0 — Chat Template & Modelfile

**3.1 Chat template is ChatML.** [VERIFIED: huggingface.co/dicta-il/DictaLM-3.0-Nemotron-12B-Instruct/raw/main/chat_template.jinja]

Format (when `add_generation_prompt=True`):
```
<|im_start|>system
{custom_instructions OR default Hebrew assistant identity}<|im_end|>
<|im_start|>user
{user content}<|im_end|>
<|im_start|>assistant
```

Special tokens: `<|im_start|>` (id 20), `<|im_end|>` (id 21), `<s>` BOS (auto-added), `</s>` EOS. The template **DOES** support a system message — DictaLM 2.0 advice ("no system prompt, mistral template") is stale and does NOT apply.

**3.2 Existing Modelfile is correct.** `scripts/ollama/DictaLM3.Modelfile` (Phase 1) relies on auto-detection of `tokenizer.chat_template` GGUF metadata. Verified working approach per [CITED: huggingface.co/docs/hub/ollama]. Conservative defaults already set: `temperature=0.3`, `num_ctx=8192`, `num_predict=256`, `keep_alive=-1`.

**3.3 PARAMETER overrides for Phase 3.** Override at chat-call-time, not in Modelfile, so the same registered `dictalm3` model serves both grounded suggestions (low temp) and any future creative tasks:

| Setting | Value | Rationale |
|---------|-------|-----------|
| `temperature` | `0.0` | Grounding requires deterministic output (#5 pitfall mitigation; aligns with Ollama's structured-output guidance "set temperature to 0" [CITED: ollama.com/blog/structured-outputs]) |
| `num_predict` | `512` | Hebrew text is ~25% denser per UTF-8 byte than English; 512 tokens ≈ 2-3 suggestion cards. Modelfile default 256 is too tight for citations |
| `num_ctx` | `8192` | Fits transcript (~200 tokens) + 5 retrieved chunks (~6000 tokens at Hebrew density) + system prompt + few-shot + headroom |
| `top_p` | `0.9` | Per Ollama Options reference [CITED: ollama-python README] |
| `stop` | `["<|im_end|>"]` | Defense-in-depth — Modelfile auto-detection should handle this, but explicit stop guards against any auto-template miss |

**3.4 Ollama version requirements.** Structured outputs (`format=<json-schema>`) introduced in **Ollama 0.5** (December 2024) [VERIFIED: dev.to/busycaesar — "Ollama 0.5 Is Here: Generate Structured Outputs"; CITED: ollama.com/blog/structured-outputs]. Phase 1 locked Ollama as a host-native install via `brew install ollama`; current Homebrew Ollama is well past 0.5, so the planner can lock this requirement without further user confirmation.

**3.5 Streaming + structured outputs caveat — CRITICAL.** [VERIFIED: github.com/ollama/ollama issues #14440 + #15260; multiple 2026 reports]

When `format=<schema>` AND `stream=true` are passed together:
- Ollama tries to enforce the schema but the constraint **does not strictly hold mid-stream**, especially with thinking/reasoning models or `gemma`-class models.
- Observed failure: model returns JSON wrapped in markdown fences, or breaks schema in a way validation catches only at final assembly.
- For non-reasoning models (DictaLM 3.0 is not a reasoning model — no `<think>` blocks emitted at runtime), this is mostly stable but still NOT a guarantee.

**Decision (locked for the planner):** Phase 3 sends `stream=True` for token-delivery latency benefits but does NOT pass `format=<schema>`. The system prompt + few-shot examples carry JSON formatting responsibility, and we validate on completion. This is the same pattern Phase 5 hot-path will consume. The price is one parse step at end-of-stream; the benefit is correctness.

### 4. Suggestion Schema (LLM-04)

**4.1 Pydantic v2 models** (matching Phase 2's pydantic-style discriminated-union event pattern):

```python
# backend/src/receptra/llm/schema.py
from __future__ import annotations
from pydantic import BaseModel, Field, ConfigDict


class Suggestion(BaseModel):
    """A single grounded reply suggestion the agent may read aloud."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str = Field(..., description="Hebrew suggestion text, ≤ 280 chars")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Self-reported model confidence")
    citation_ids: list[str] = Field(
        default_factory=list,
        description="Stable chunk IDs from RAG retrieval; empty list = no grounding",
    )


class SuggestionResponse(BaseModel):
    """Final assembled output the engine validates against."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    suggestions: list[Suggestion] = Field(..., min_length=1, max_length=3)
```

**4.2 `confidence` semantics — self-reported, NOT logprobs-derived.** [DECISION]

Self-reported confidence (LLM emits a 0.0-1.0 float in JSON) is:
- ✅ Pragmatic for v1 — works with any local model uniformly
- ✅ Consumed by Phase 6 UI to color/order suggestion cards
- ❌ Less calibrated than logprobs-based methods

Logprobs-based confidence (added to Ollama Python in v0.6.1 [VERIFIED: github.com/ollama/ollama-python releases]) is more accurate but requires `logprobs=true` parameter and post-processing. **Recommendation for Phase 3:** self-reported. Add `logprobs` instrumentation to the SQLite audit row (one new column: `mean_logprob`) so Phase 7 can correlate self-reported confidence with logprob-derived confidence on the eval set. Don't expose logprobs on the wire to Phase 6.

**4.3 `citation_ids` shape.** Stable string IDs assigned by Phase 4 RAG. Until Phase 4 lands, the CLI harness accepts a `--context-file` JSON of the shape:

```json
[
  {"id": "kb-2026-04-policy-001", "text": "מדיניות החזרים: ..."},
  {"id": "kb-2026-04-policy-002", "text": "..."}
]
```

This shape is the contract Phase 4 RAG retrieval will emit (`ChunkRef = {id: str, text: str, source: dict}`). Phase 3 only needs `id` + `text`; `source` metadata flows through Phase 4 → Phase 5 → Phase 6 (frontend citation chips).

**4.4 Streaming event types** (consumed by Phase 5 hot-path WebSocket muxer; NOT by Phase 3 directly):

```python
# backend/src/receptra/llm/schema.py (continued)
from typing import Literal, Annotated, Union
from pydantic import Field as PydField


class TokenEvent(BaseModel):
    """Streamed token delta. Phase 5 forwards to Phase 6 UI for typewriter rendering."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    type: Literal["token"] = "token"
    delta: str


class CompleteEvent(BaseModel):
    """Final parsed structured output."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    type: Literal["complete"] = "complete"
    suggestions: list[Suggestion]
    ttft_ms: int
    total_ms: int
    model: str  # which model actually served (dictalm3 vs qwen fallback)


class LlmErrorEvent(BaseModel):
    """Typed error envelope; Phase 5 maps onto WS error frames."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    type: Literal["error"] = "error"
    code: Literal["ollama_unreachable", "parse_error", "timeout", "no_context"]
    detail: str


SuggestionEvent = Annotated[
    Union[TokenEvent, CompleteEvent, LlmErrorEvent],
    PydField(discriminator="type"),
]
```

This mirrors Plan 02-04's `SttEvent` discriminated-union pattern exactly — same TypeAdapter idiom for Phase 5 muxing.

### 5. Hebrew Prompt Template

**5.1 System prompt — written in Hebrew.** [DECISION, MEDIUM confidence — research consensus is split]

Trade-off:
- **Hebrew system prompt** (recommended): better in-language alignment with DictaLM 3.0 (Hebrew-native model), reduces code-switching artifacts.
- **English system prompt**: most published prompt-engineering examples are in English; easier for international contributors to read/tune; Qwen 2.5 fallback is a multilingual model that may follow English instructions slightly better.

**Recommendation:** Hebrew system prompt by default, English fallback variant available behind a `LLM_SYSTEM_PROMPT_LANG=en` env var. This belongs in Phase 7 prompt-tuning A/B; for Phase 3 we ship Hebrew and instrument enough to compare later.

**5.2 Canonical Hebrew system prompt** (locked draft — Phase 7 will tune):

```
אתה עוזר וירטואלי לסוכן שירות לקוחות בשיחה טלפונית בעברית.
תפקידך: לקרוא את התמלול של מה שהלקוח אמר ולהציע לסוכן עד שלוש תשובות קצרות, מדויקות, ובסגנון אנושי בעברית.

חוקים מחייבים:
1. השתמש אך ורק במידע שמופיע בקטעי הידע המסומנים <context>...</context>. אל תמציא עובדות עסקיות.
2. אם המידע ב-<context> אינו מספיק כדי לענות, החזר תשובה אחת בלבד עם הטקסט "אין לי מספיק מידע" וציטוטים ריקים.
3. כל תשובה חייבת להיות עד 280 תווים, בעברית טבעית, מנוסחת כמו אדם אמיתי.
4. החזר את התשובה כ-JSON תקין בלבד, ללא טקסט נוסף לפני או אחרי, בפורמט:
{"suggestions":[{"text":"...","confidence":0.0,"citation_ids":["..."]}]}
5. citation_ids חייב להכיל את ה-id המדויק של קטע ה-<context> שעליו התשובה מבוססת.
6. confidence הוא מספר בין 0.0 ל-1.0 שמשקף עד כמה הקטעים מספקים מענה ישיר.
```

(English gloss — DO NOT include in the actual prompt: "You are a virtual assistant for a Hebrew customer-service agent. Read the customer transcript and suggest up to three short, accurate, human-sounding Hebrew replies. Rules: 1) Use only `<context>` info; don't fabricate. 2) If `<context>` is insufficient, return one suggestion with text 'אין לי מספיק מידע' and empty citations. 3) ≤280 chars, natural Hebrew. 4) Return ONLY valid JSON. 5) `citation_ids` must reference exact `<context>` ids used. 6) `confidence` is 0.0-1.0.")

**5.3 User-message format:**

```
<context>
[id: kb-001]
{chunk text in Hebrew}

[id: kb-002]
{chunk text in Hebrew}
</context>

<transcript>
{the agent-side transcript line — usually a customer utterance}
</transcript>
```

Numbered `[id: ...]` markers per chunk (NOT XML attributes — DictaLM is stronger on inline-marker patterns than on XML-attribute parsing per general LLM prompt-engineering convention). The model is instructed to copy these IDs verbatim into `citation_ids`.

**5.4 Few-shot examples (TWO, prepended as alternating user/assistant turns):**

*Few-shot 1 — grounded reply:*

User content:
```
<context>
[id: kb-policy-returns]
מדיניות החזרים: ניתן להחזיר מוצר תוך 14 יום מיום הקנייה עם החשבונית המקורית.
</context>

<transcript>
תוך כמה זמן אני יכול להחזיר מוצר?
</transcript>
```

Assistant content (verbatim):
```json
{"suggestions":[{"text":"ניתן להחזיר את המוצר תוך 14 ימים מיום הקנייה, ויש להציג את החשבונית המקורית.","confidence":0.95,"citation_ids":["kb-policy-returns"]}]}
```

*Few-shot 2 — insufficient context refusal:*

User content:
```
<context>
[id: kb-policy-returns]
מדיניות החזרים: ניתן להחזיר מוצר תוך 14 יום מיום הקנייה עם החשבונית המקורית.
</context>

<transcript>
מה שעות הפעילות של החנות?
</transcript>
```

Assistant content (verbatim):
```json
{"suggestions":[{"text":"אין לי מספיק מידע","confidence":0.0,"citation_ids":[]}]}
```

These two examples are the ENTIRE prompt-engineering footprint Phase 3 ships — Phase 7 evals add or modify examples based on the 20-example accept-rate review. [DECISION]

**5.5 Grounding patterns (LLM-03).**

Three layered defenses, in order of strength:

1. **Hard short-circuit:** if `context_chunks == []` or `len(transcript.strip()) == 0`, the engine SKIPS the LLM call entirely and synthesizes the canonical refusal directly. Saves ~2 s of model time and removes any chance the model fabricates from few-shot memory. [DECISION — LLM-03 hardest-case path]

2. **Explicit refusal instruction:** rule #2 in §5.2.

3. **Few-shot demonstration:** §5.4 example #2 shows the exact JSON shape for refusal.

The combination of (1)+(2)+(3) is the standard 2026 pattern for production grounding [CITED: aiamastery.substack.com — "Lesson 25: Advanced Prompting for RAG"; CITED: apxml.com/courses/getting-started-rag — "Structuring Prompts for RAG Systems"].

**5.6 What `confidence` should signal (not enforced, prompted):** the prompt instructs the model that confidence "reflects how directly the chunks answer the question" — for a refusal it must be `0.0`, for a perfect match `≥ 0.9`, for a partial answer somewhere in between. Phase 7 prompt-tuning will calibrate this against the eval set. [ASSUMED — self-reported confidence calibration is generally weak; we accept this for v1 and instrument for later analysis]

### 6. Backend Integration (LLM-02 + LLM-05)

**6.1 Package layout** (mirrors `receptra.stt` package structure exactly):

```
backend/src/receptra/llm/
├── __init__.py
├── client.py          # AsyncClient wrapper, host config, timeout, retry
├── prompts.py         # SYSTEM_PROMPT_HE, FEW_SHOTS, build_user_message()
├── schema.py          # Suggestion, SuggestionResponse, *Event union
├── engine.py          # generate_suggestions() AsyncGenerator orchestration
├── metrics.py         # LlmCallMetrics frozen dataclass + log_llm_call()
└── audit.py           # init_llm_audit_table() + insert_llm_call() (extends existing audit DB)
```

**6.2 Internal interface contract (LLM-02):**

```python
# backend/src/receptra/llm/engine.py
from collections.abc import AsyncGenerator
from receptra.llm.schema import SuggestionEvent
from receptra.rag.types import ChunkRef  # forward-declared by Phase 4; Phase 3 ships its own dataclass


async def generate_suggestions(
    transcript: str,
    context_chunks: list[ChunkRef],
    *,
    request_id: str | None = None,
    model: str | None = None,  # default settings.llm_model_tag = "dictalm3"
) -> AsyncGenerator[SuggestionEvent, None]:
    """Stream suggestion events for one (transcript, context) pair.

    Yields TokenEvent(...) for each non-empty content delta, then exactly one
    CompleteEvent at end-of-stream (after JSON parse + retry), OR exactly one
    LlmErrorEvent if Ollama is unreachable / parse retry exhausted.

    Phase 5 hot-path muxes these onto /ws/agent. CLI harness (Phase 3 §7) prints
    them. RAG (Phase 4) calls this directly with retrieved chunks.
    """
    ...
```

**Algorithm sketch:**

1. `t_start = time.perf_counter()`; assign `request_id = request_id or uuid4().hex`.
2. **Short-circuit refusal** (§5.5 defense 1): if `not context_chunks or not transcript.strip()`, yield `CompleteEvent(suggestions=[Suggestion(text="אין לי מספיק מידע", confidence=0.0, citation_ids=[])], ttft_ms=0, ...)` and return.
3. Build messages: system prompt + 2 few-shot turns + final user turn (§5.3).
4. `await client.chat(model=..., messages=..., stream=True, options=...)`.
5. **Stream loop:** buffer `accumulated = []`; yield `TokenEvent(delta=chunk["message"]["content"])` for each non-empty delta; record `ttft_ms` on the first non-empty delta.
6. **Parse on done:** join `accumulated`, strip markdown fences if present (defense — see #4 above), `SuggestionResponse.model_validate_json(text)`.
7. **Parse failure path (bounded retry):** on `pydantic.ValidationError` or `json.JSONDecodeError`, make ONE non-streaming retry with a stricter system prompt suffix "החזר אך ורק JSON תקין, ללא Markdown, ללא הסברים" and `format="json"` (Ollama generic JSON mode — works without schema). If that ALSO fails, yield `LlmErrorEvent(code="parse_error", detail=...)` and synthesize the canonical refusal as a `CompleteEvent` so consumers always get one terminal event.
8. **Yield `CompleteEvent`** with parsed suggestions, `ttft_ms`, `total_ms`, `model`.
9. **Always log + audit:** call `log_llm_call(metrics)` + `insert_llm_call(audit_db, metrics)` in a `finally` block, both wrapped in independent try/except so logging/DB failure cannot crash callers (mirrors Plan 02-06 pattern).

**6.3 TTFT pattern (LLM-05):**

```python
# backend/src/receptra/llm/metrics.py
from __future__ import annotations
import time
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class LlmCallMetrics:
    request_id: str
    model: str  # actual model that served (dictalm3 / qwen2.5:7b)
    transcript_hash: str  # sha256 of transcript[:8] — not the raw text
    n_chunks: int
    t_request_sent: float  # perf_counter monotonic
    t_first_token: float | None  # None if no tokens streamed (error path)
    t_done: float
    eval_count: int | None  # from final chunk
    prompt_eval_count: int | None
    status: Literal["ok", "parse_retry_ok", "parse_error", "timeout", "ollama_unreachable", "no_context"]
    suggestions_count: int  # 0 on error
    grounded: bool  # at least one suggestion has non-empty citation_ids

    @property
    def ttft_ms(self) -> int:
        if self.t_first_token is None:
            return -1  # sentinel for "no token ever arrived"
        return int((self.t_first_token - self.t_request_sent) * 1000)

    @property
    def total_ms(self) -> int:
        return int((self.t_done - self.t_request_sent) * 1000)
```

**Wall-clock TTFT vs Ollama-reported `prompt_eval_duration`:** track BOTH. The wall-clock is what Phase 5 latency budget cares about; the Ollama-internal field shows the prompt-eval slice independent of network/Python overhead. Audit row stores both for Phase 7 analysis. [DECISION]

**6.4 SQLite audit table** (extends `data/audit.sqlite` from Plan 02-06):

```sql
CREATE TABLE IF NOT EXISTS llm_calls (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id      TEXT    NOT NULL,
    transcript_hash TEXT    NOT NULL,
    model           TEXT    NOT NULL,
    n_chunks        INTEGER NOT NULL,
    ttft_ms         INTEGER NOT NULL,
    total_ms        INTEGER NOT NULL,
    eval_count      INTEGER,
    prompt_eval_count INTEGER,
    suggestions_count INTEGER NOT NULL,
    grounded        INTEGER NOT NULL,  -- 0/1
    status          TEXT    NOT NULL,
    ts              TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_llm_calls_ts ON llm_calls(ts);
CREATE INDEX IF NOT EXISTS idx_llm_calls_status ON llm_calls(status);
```

`receptra.llm.audit` mirrors `receptra.stt.audit` exactly: stdlib `sqlite3`, `with sqlite3.connect(...)`, parent-dir lazy creation, idempotent CREATE, no async DB driver. [DECISION — same constraints as Plan 02-06]

**PII boundary:** transcripts are PII (RESEARCH §Security Domain Plan 02-02). The audit row stores `transcript_hash` (sha256 first 8 hex chars) NOT raw text; loguru `log_llm_call` event by default redacts the transcript. Override with `RECEPTRA_LLM_LOG_TEXT_REDACTION_DISABLED=true` for local debugging only — same default-on PII redaction Plan 02-06 established for STT. [DECISION]

**6.5 Settings additions** (extend `backend/src/receptra/config.py`):

```python
# --- Phase 3 LLM ---
llm_model_tag: str = "dictalm3"  # primary
llm_model_fallback: str = "qwen2.5:7b"  # fallback when primary unavailable
llm_temperature: float = 0.0
llm_num_predict: int = 512
llm_num_ctx: int = 8192
llm_top_p: float = 0.9
llm_request_timeout_s: float = 30.0
llm_system_prompt_lang: Literal["he", "en"] = "he"  # Phase 7 A/B
llm_log_text_redaction_disabled: bool = False  # PII default-on
```

All RECEPTRA_-prefixed env-var-tunable. Document in `.env.example` per repo convention.

**6.6 Fallback model selection.** Engine startup probe (§2.2): `await client.list()` → if `dictalm3` present, use it; else if `qwen2.5:7b` present, use it and emit a one-time WARN log; else operate in "permanent insufficient-context refusal" mode and emit ERROR on every call. `model` field in `CompleteEvent` always reflects what actually served, so Phase 6 UI can surface "(fallback model)" if needed.

### 7. CLI Harness (LLM-06)

**7.1 Goal.** Run the full suggestion engine end-to-end, completely independent of STT, against a checked-in fixture set. Two use cases:

- **Dev tuning:** `python scripts/eval_llm.py --transcript "..." --context-file fixtures/llm/policy.json` and inspect the JSON output + TTFT printed to stdout.
- **Phase 7 prompt eval:** loop over an eval set (`fixtures/llm/eval_set.jsonl`) and print summary stats.

**7.2 Spec:**

```bash
# Single-shot mode
python scripts/eval_llm.py \
    --transcript "תוך כמה זמן אני יכול להחזיר מוצר?" \
    --context-file fixtures/llm/policy_returns.json \
    [--model dictalm3] \
    [--ollama-host http://localhost:11434] \
    [--system-prompt-lang he] \
    [--no-stream]  # disable token-delta printing, only emit final JSON
```

stdout: pretty-printed `CompleteEvent` JSON + a final line `TTFT: 312 ms  TOTAL: 1845 ms  MODEL: dictalm3  GROUNDED: true`.
stderr (when `--stream` default on): each `TokenEvent.delta` printed inline as it arrives — visual TTFT confirmation.

```bash
# Eval-set mode (Phase 7 will heavily exercise this)
python scripts/eval_llm.py --eval-set fixtures/llm/eval_set.jsonl \
    [--out-jsonl results/llm_eval.jsonl]
```

Each line of `eval_set.jsonl`:
```json
{"id":"eval-001","transcript":"...","context":[{"id":"kb-001","text":"..."}],"expected":{"grounded":true,"refusal":false}}
```

Output rolls up: count, mean TTFT, p95 TTFT, refusal rate, grounded rate, parse-retry rate, parse-error rate. Phase 7 consumes this directly for DEMO-02.

**7.3 Critical: harness MUST NOT import `receptra.stt`.** The harness imports only `receptra.llm` + `receptra.config`. This proves LLM-06's "independent of STT pipeline" structurally; a regression test asserts `import scripts.eval_llm` does not transitively import `faster_whisper` or `silero_vad`. [DECISION]

**7.4 Fixture directory:**

```
fixtures/llm/
├── policy_returns.json       # 1-chunk grounded fixture
├── policy_hours.json         # 1-chunk INSUFFICIENT fixture (returns refusal)
├── empty_context.json        # 0-chunk fixture (short-circuit path)
└── eval_set.jsonl            # Phase 7 — start with 5 lines, grow to 20
```

JSON shapes match §4.3. Fixtures committed; not gitignored. Phase 7 prompt-tuning expands the set.

### 8. Memory Pressure (Pitfall #3)

**8.1 Already addressed in Phase 1.** Plan 01-05 OPEN-2 locked DictaLM Q4_K_M (7.49 GB) as default for 16 GB Macs; Q5_K_M (8.76 GB) override available via `DICTALM_QUANT=Q5_K_M make models` for 32 GB. Documented in `docs/models.md` (Phase 1).

**8.2 Phase 3 verification step.** Add to `docs/llm.md`: a runtime check `ollama ps` shows DictaLM 3.0 loaded with VSZ within budget (≈9-10 GB during inference per Phase 1 RESEARCH §11). If `ollama ps` shows DictaLM evicted under memory pressure (e.g., during simultaneous Whisper inference), recommend Qwen 2.5 7B fallback OR M2 Pro 32 GB hardware.

**8.3 `keep_alive=-1`** in DictaLM3.Modelfile (Phase 1) means Ollama pins weights forever, eliminating cold-load on every request but increasing baseline memory. Combined with Whisper (~1.5 GB) + BGE-M3 in Phase 4 (~1.2 GB) + OS + browser, the 16 GB M2 floor is tight. Phase 3 doesn't change this — it relies on Phase 1's decision. The chaos test in §11 includes an OOM-simulation by mocking `ollama_unreachable` errors.

### 9. State of the Art (2026)

| Old approach | Current approach | When changed | Impact for us |
|--------------|------------------|--------------|---------------|
| Prompt-only JSON (regex parsing, retries) | Ollama `format=<JSON-Schema>` for non-streaming | Ollama 0.5 (Dec 2024) | We use prompt+parse for streaming + grace-fallback to `format="json"` on retry |
| Strict JSON-mode wrappers (instructor, ollama-instructor) | Native Ollama format param | Ollama 0.5+ | No third-party dep; Pydantic schema lives in our code |
| `format="json"` only (loose JSON) | `format=<schema>` (typed JSON) | Ollama 0.5+ | We use loose mode in retry path because `format=schema` + stream is unreliable |
| LLM does retrieval (long-context cram) | RAG-then-LLM with explicit `<context>` | Throughout 2025 | Phase 3 expects pre-retrieved chunks from Phase 4 |

Deprecated/avoid:
- `format="json"` from before Ollama 0.5 (returns generic loose JSON; useful as our retry-path fallback only).
- Hand-rolled regex JSON extraction (`re.search(r'\{.*\}', text)`) — fragile against partial markdown; Pydantic `model_validate_json` after `.strip()` + fence-removal is the 2026 idiom.
- Telling DictaLM "use mistral-instruct template, no system prompt" — applies to DictaLM 2.0, NOT 3.0.

## Recommended Dependencies

Add to `backend/pyproject.toml` `[project].dependencies`:

| Package | Version | License | Why |
|---------|---------|---------|-----|
| `ollama` | `>=0.6.1,<1` | MIT | Official client, AsyncClient, structured outputs support [VERIFIED: pypi.org/project/ollama] |

Test/dev dependencies — already present from Phase 2: `pytest`, `pytest-asyncio`, `httpx`. No new dev deps required (pydantic + loguru already pinned).

**Intentionally NOT added:**
- `instructor` / `ollama-instructor` — Pydantic-native validation in our own code is sufficient; adding instructor pulls in extra retry logic we don't need and more deps to license-check.
- `pydantic-ai` — designed for agentic flows; we have one prompt + one parse, not an agent loop. Overkill for v1.
- `langchain` / `langchain-ollama` — heavy, license-mixed surface, and we already have a typed event union we don't want to bend to LangChain's chain abstraction.

## Suggestion Schema (Pydantic) — full reference

Reproduced for the planner's convenience (canonical version is §4.1 + §4.4):

```python
# backend/src/receptra/llm/schema.py
from __future__ import annotations
from typing import Annotated, Literal, Union
from pydantic import BaseModel, ConfigDict, Field


class Suggestion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    text: str = Field(..., description="Hebrew suggestion text, ≤ 280 chars")
    confidence: float = Field(..., ge=0.0, le=1.0)
    citation_ids: list[str] = Field(default_factory=list)


class SuggestionResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    suggestions: list[Suggestion] = Field(..., min_length=1, max_length=3)


class TokenEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    type: Literal["token"] = "token"
    delta: str


class CompleteEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    type: Literal["complete"] = "complete"
    suggestions: list[Suggestion]
    ttft_ms: int
    total_ms: int
    model: str


class LlmErrorEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    type: Literal["error"] = "error"
    code: Literal["ollama_unreachable", "parse_error", "timeout", "no_context"]
    detail: str


SuggestionEvent = Annotated[
    Union[TokenEvent, CompleteEvent, LlmErrorEvent],
    Field(discriminator="type"),
]
```

## Prompt Template Reference

(See §5.2 + §5.4 for canonical content; this is a usage-pattern reference for the planner.)

```python
# backend/src/receptra/llm/prompts.py
from __future__ import annotations
from receptra.rag.types import ChunkRef  # Phase 4 forward-decl; Phase 3 ships local stub


SYSTEM_PROMPT_HE = """אתה עוזר וירטואלי לסוכן שירות לקוחות בשיחה טלפונית בעברית.
... (full text per §5.2)"""

# Few-shot turns formatted as ChatML messages
FEW_SHOTS_HE: list[dict[str, str]] = [
    {"role": "user", "content": "...few-shot 1 user content (§5.4)..."},
    {"role": "assistant", "content": '{"suggestions":[{"text":"...","confidence":0.95,"citation_ids":["kb-policy-returns"]}]}'},
    {"role": "user", "content": "...few-shot 2 user content (§5.4)..."},
    {"role": "assistant", "content": '{"suggestions":[{"text":"אין לי מספיק מידע","confidence":0.0,"citation_ids":[]}]}'},
]


def build_user_message(transcript: str, context_chunks: list[ChunkRef]) -> str:
    """Render a single user message with <context>...</context> + <transcript>...</transcript>."""
    if not context_chunks:
        ctx_block = "<context>\n(אין קטעי הקשר זמינים)\n</context>"
    else:
        rendered = "\n\n".join(f"[id: {c.id}]\n{c.text}" for c in context_chunks)
        ctx_block = f"<context>\n{rendered}\n</context>"
    return f"{ctx_block}\n\n<transcript>\n{transcript}\n</transcript>"


def build_messages(transcript: str, context_chunks: list[ChunkRef], lang: Literal["he","en"]="he") -> list[dict[str,str]]:
    system = SYSTEM_PROMPT_HE if lang == "he" else SYSTEM_PROMPT_EN
    return [
        {"role": "system", "content": system},
        *FEW_SHOTS_HE,
        {"role": "user", "content": build_user_message(transcript, context_chunks)},
    ]
```

## TTFT Instrumentation Pattern

```python
# backend/src/receptra/llm/engine.py — sketch only
import time
from collections.abc import AsyncGenerator
from contextlib import suppress
from hashlib import sha256
from uuid import uuid4

from loguru import logger
from pydantic import ValidationError

from receptra.config import settings
from receptra.llm.client import get_async_client
from receptra.llm.schema import (
    CompleteEvent, LlmErrorEvent, SuggestionEvent, SuggestionResponse, TokenEvent,
)
from receptra.llm.prompts import build_messages
from receptra.llm.metrics import LlmCallMetrics, log_llm_call
from receptra.llm.audit import insert_llm_call


async def generate_suggestions(transcript, context_chunks, *, request_id=None, model=None) -> AsyncGenerator[SuggestionEvent, None]:
    request_id = request_id or uuid4().hex
    model = model or settings.llm_model_tag
    t_start = time.perf_counter()
    t_first_token: float | None = None
    accumulated: list[str] = []
    status = "ok"
    eval_count = prompt_eval_count = None

    # §5.5 short-circuit
    if not context_chunks or not transcript.strip():
        yield CompleteEvent(
            suggestions=[Suggestion(text="אין לי מספיק מידע", confidence=0.0, citation_ids=[])],
            ttft_ms=0, total_ms=int((time.perf_counter() - t_start) * 1000), model=model,
        )
        # log + return
        return

    client = await get_async_client()
    messages = build_messages(transcript, context_chunks, lang=settings.llm_system_prompt_lang)

    try:
        stream = await client.chat(
            model=model, messages=messages, stream=True,
            options={
                "temperature": settings.llm_temperature,
                "num_predict": settings.llm_num_predict,
                "num_ctx": settings.llm_num_ctx,
                "top_p": settings.llm_top_p,
                "stop": ["<|im_end|>"],
            },
        )
        async for chunk in stream:
            delta = chunk["message"]["content"]
            if delta:
                if t_first_token is None:
                    t_first_token = time.perf_counter()
                accumulated.append(delta)
                yield TokenEvent(delta=delta)
            if chunk.get("done"):
                eval_count = chunk.get("eval_count")
                prompt_eval_count = chunk.get("prompt_eval_count")

        # Parse + retry path — see §6.2 step 7 for full algorithm
        text = "".join(accumulated).strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            parsed = SuggestionResponse.model_validate_json(text)
        except (ValidationError, ValueError):
            status = "parse_retry_ok"  # downgraded if retry succeeds
            parsed = await _retry_parse_strict(client, model, messages)
            if parsed is None:
                status = "parse_error"
                t_done = time.perf_counter()
                yield LlmErrorEvent(code="parse_error", detail="JSON parse failed after retry")
                yield CompleteEvent(
                    suggestions=[Suggestion(text="אין לי מספיק מידע", confidence=0.0, citation_ids=[])],
                    ttft_ms=int((t_first_token - t_start) * 1000) if t_first_token else -1,
                    total_ms=int((t_done - t_start) * 1000), model=model,
                )
                return

        t_done = time.perf_counter()
        yield CompleteEvent(
            suggestions=list(parsed.suggestions),
            ttft_ms=int((t_first_token - t_start) * 1000) if t_first_token else -1,
            total_ms=int((t_done - t_start) * 1000),
            model=model,
        )

    except (httpx.ConnectError, httpx.ReadTimeout) as exc:
        status = "ollama_unreachable" if isinstance(exc, httpx.ConnectError) else "timeout"
        yield LlmErrorEvent(code=status, detail=str(exc))
        return
    finally:
        # Wrap in suppress — logging/audit failures must not crash callers
        with suppress(Exception):
            metrics = LlmCallMetrics(
                request_id=request_id, model=model,
                transcript_hash=sha256(transcript.encode("utf-8")).hexdigest()[:16],
                n_chunks=len(context_chunks),
                t_request_sent=t_start, t_first_token=t_first_token,
                t_done=time.perf_counter(),
                eval_count=eval_count, prompt_eval_count=prompt_eval_count,
                status=status,
                suggestions_count=...,  # set from parsed if available
                grounded=...,  # any non-empty citation_ids
            )
            log_llm_call(metrics)
            insert_llm_call(settings.audit_db_path, metrics)
```

This is a sketch — the planner's tasks turn it into atomic TDD steps. The structure mirrors `receptra.stt.pipeline.run_utterance_loop` from Plan 02-04 deliberately so readers don't context-switch between phases.

## CLI Harness Spec

Per §7. Full spec:

- **Path:** `scripts/eval_llm.py`
- **Invocation:** `uv run python scripts/eval_llm.py [args]` from repo root
- **Argparse flags:** `--transcript`, `--context-file`, `--eval-set`, `--out-jsonl`, `--model`, `--ollama-host`, `--system-prompt-lang`, `--no-stream`
- **Single-shot output (stdout):** pretty-printed CompleteEvent JSON + summary line
- **Streaming output (stderr):** TokenEvent deltas printed inline (only when `--stream` default on)
- **Eval-set output (stdout):** JSONL one result per line + final aggregate stats
- **Exit codes:** 0 = success (any combination of grounded/refusal acceptable), 1 = ollama unreachable, 2 = parse error rate above threshold (default 5% — flag for prompt-tuning attention)
- **STT independence:** `assert "receptra.stt" not in sys.modules` regression test; harness imports only `receptra.llm.*` + `receptra.config`

## Don't Hand-Roll

| Problem | Don't build | Use instead | Why |
|---------|-------------|-------------|-----|
| HTTP client to Ollama | Custom httpx wrapper with retries | `ollama.AsyncClient` | Official, types match server, releases stay in sync |
| ChatML template rendering | Format `<|im_start|>...<|im_end|>` strings ourselves | Ollama auto-detects from GGUF tokenizer.chat_template | Modelfile already declares this; manual rendering re-introduces drift |
| JSON schema validation | Hand-rolled regex / json.loads + manual checks | Pydantic `model_validate_json` | Same library Phase 2 uses; integrates with mypy strict |
| Retry on parse failure | Loop with arbitrary backoff | Bounded 1-retry with `format="json"` | Each retry is ~2 s LLM time; bound is non-negotiable for Phase 5 latency |
| Confidence calibration | Hand-tuned probability ranges | Self-reported in v1 + logprob audit for Phase 7 | Calibration is a research problem; v1 ships and instruments |
| TTFT measurement | Instrument inside Ollama or parse server logs | `time.perf_counter()` around the call | Same pattern Plan 02-06 uses for STT — symmetry helps debugging |
| Audit logging | New table per phase | Extend existing `data/audit.sqlite` | Phase 5 INT-05 wants single audit DB across pipeline |

## Common Pitfalls

### Pitfall A: Treating streaming + format=schema as a guarantee
**What goes wrong:** Plan assumes `format=Suggestion.model_json_schema()` + `stream=true` produces validated JSON; consumer crashes mid-call when model emits markdown fence.
**Why:** Upstream issue #14440 — schema enforcement is best-effort under streaming.
**Avoid:** §3.5 decision — DON'T pass `format=schema` while streaming. Parse on completion. Bounded retry path.
**Detect early:** §11 chaos test injects malformed JSON via mocked client; assert one retry, then graceful refusal.

### Pitfall B: Using DictaLM 2.0 chat-template advice for 3.0
**What goes wrong:** Plan tells the LLM "no system prompt, mistral template" because Hugging Face docs for DictaLM 2.0 say so; DictaLM 3.0 ignores all instructions and produces wrong-language output.
**Why:** DictaLM 3.0 uses ChatML (verified `chat_template.jinja`); 2.0 used mistral-instruct.
**Avoid:** Trust Phase 3 RESEARCH §3.1; never copy-paste from generic DictaLM tutorials.
**Detect early:** §11 contract test asserts the model's response to a Hebrew query with system prompt is non-empty Hebrew JSON.

### Pitfall C: Blocking the FastAPI event loop
**What goes wrong:** Plan uses sync `ollama.chat()` instead of `AsyncClient`; one in-flight LLM call freezes the entire backend including the STT WebSocket hot path.
**Why:** FastAPI is async-native; Pipecat in Phase 5 will compound this.
**Avoid:** §1.1 — `AsyncClient` everywhere. Engine is `async def`. CLI harness wraps in `asyncio.run`.
**Detect early:** §11 chaos test (concurrent STT WS + LLM call) — both must remain responsive.

### Pitfall D: PII leak via transcripts in logs
**What goes wrong:** loguru `log_llm_call` includes raw transcript by default; bug reports include the audit log; user data leaks.
**Why:** Plan 02-06 already established this for STT — must extend to LLM.
**Avoid:** §6.4 — store `transcript_hash` not text; redaction default-on; `RECEPTRA_LLM_LOG_TEXT_REDACTION_DISABLED=true` opt-in only.
**Detect early:** §11 regression test asserts default log line does NOT contain transcript text.

### Pitfall E: CLI harness silently importing STT
**What goes wrong:** `scripts/eval_llm.py` imports `receptra.config`, which transitively pulls `receptra.stt.engine` (because some refactor added a circular dep), and the harness ends up loading Whisper. Now the harness needs the model directory mounted, defeating LLM-06.
**Why:** Python import side effects.
**Avoid:** §7.3 — explicit regression test `assert "receptra.stt" not in sys.modules` after harness import.
**Detect early:** §11 structural test enumerates harness-side imports.

### Pitfall F: Memory pressure from co-resident models
**What goes wrong:** DictaLM 12B Q4 + Whisper turbo + BGE-M3 + browser exceeds 16 GB on M2; Ollama swaps weights or evicts; latency spikes from <500 ms TTFT to 5+ s.
**Why:** §8 — Phase 1 OPEN-2 chose Q4_K_M for this reason; users may override.
**Avoid:** Document `ollama ps` runtime check; provide Qwen 2.5 7B fallback path; honor `keep_alive=-1` from Phase 1 Modelfile.
**Detect early:** Phase 7 latency baseline run on M2 16 GB hardware confirms TTFT p95.

### Pitfall G: Cold-start TTFT vs warm TTFT divergence
**What goes wrong:** First LLM call after Ollama process restart costs ~5 s (Modelfile load); subsequent calls are <500 ms. Plan's TTFT instrumentation aggregates both, hiding the cold-start outlier.
**Why:** `keep_alive=-1` mitigates but the first-ever call still pays load cost.
**Avoid:** Engine startup probe (§2.2) issues a warmup call (analogous to Plan 02-02 Whisper warmup); audit row records `is_warmup=true` for the warmup call so eval queries can filter it out.
**Detect early:** §11 latency test asserts warmup call < cold-start ceiling AND second call < warm ceiling.

## Project Constraints (from CLAUDE.md)

- **Hebrew first.** Every prompt-engineering choice must work in Hebrew before any English optimization. ✓ §5.1 default Hebrew.
- **Apple Silicon M2+, no CUDA.** Ollama Metal serves DictaLM 3.0 natively on host (Phase 1 OPEN-1). ✓
- **Permissive licensing only.** `ollama` Python = MIT [VERIFIED via PyPI]. DictaLM 3.0 = Apache 2.0 [VERIFIED dicta.org.il]. Qwen 2.5 = Apache 2.0 [VERIFIED]. ✓
- **Zero cloud dependency.** Local Ollama only; no `ollama.com` cloud client. AsyncClient `host=settings.ollama_host` always points at host or localhost. ✓
- **Latency:** Speech → suggestion <2 s. LLM TTFT budget <500 ms. ✓ §6.3 wall-clock instrumentation.
- **Distribution:** OSS self-host first. No hosted SaaS LLM swap. ✓
- **GSD workflow.** All file edits go through Phase 3 plans, not direct edits. ✓ research output only here.

## Runtime State Inventory

Phase 3 is greenfield code addition (new `receptra.llm` package + new `scripts/eval_llm.py`). Not a rename/refactor/migration phase. Section omitted per template.

(For honesty: the only existing-state interaction is **extending** `data/audit.sqlite` with a new `llm_calls` table — that's an additive schema change, idempotent via `CREATE TABLE IF NOT EXISTS`, not a rename. No data migration. No live-service config changes. No OS-registered state. No new secrets. No build-artifact rename.)

## Environment Availability

| Dependency | Required by | Available on dev Mac | Version | Fallback |
|-----------|-------------|----------------------|---------|----------|
| Ollama (host) | Engine + CLI harness | YES via Phase 1 `brew install ollama` | latest (well past 0.5) | None — required |
| `dictalm3` Ollama model | Primary path | YES via Phase 1 `make models` (downloads + `ollama create dictalm3`) | DictaLM-3.0-Nemotron-12B-Instruct Q4_K_M | `qwen2.5:7b` (Phase 1 `make models-fallback`) |
| Python `ollama>=0.6.1` | Backend + harness | NOT YET INSTALLED — Phase 3 adds | 0.6.1 | None — required (engine cannot ship without it) |
| Python 3.12 | Backend | YES (Phase 1) | 3.12.x | — |
| `host.docker.internal` reachable from backend container | Engine in compose | YES (`extra_hosts` declared Plan 01-04) | — | — |
| ~10 GB free RAM during inference | DictaLM 12B Q4 runtime | depends on user hardware (M2 16GB tight; M2 Pro 32 GB comfortable) | — | Qwen 2.5 7B (~5 GB) |
| `data/audit.sqlite` writable | Audit table | YES (Plan 02-06 mounted volume) | — | — |

**Missing dependencies with fallback:** DictaLM unavailable → Qwen 2.5 7B. Engine startup probe selects automatically.

**Missing dependencies with no fallback:** Ollama itself (host); Python `ollama` package (Phase 3 plan installs it).

## Validation Architecture

(`workflow.nyquist_validation: true` in `.planning/config.json` — section required.)

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.3+ + pytest-asyncio (already pinned Phase 1/2) |
| Config file | `backend/pyproject.toml` `[tool.pytest.ini_options]` (already configured `asyncio_mode = "auto"`) |
| Quick run | `cd backend && uv run pytest tests/llm/ -x` |
| Full suite | `cd backend && uv run pytest tests/` |
| CLI harness smoke | `cd <repo> && uv run --project backend python scripts/eval_llm.py --transcript "שלום" --context-file fixtures/llm/empty_context.json --no-stream` (asserts exit 0 + JSON contains "אין לי מספיק מידע") |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| LLM-01 | Engine startup probe selects `dictalm3` if present, falls back to `qwen2.5:7b` | unit (mocked AsyncClient) | `pytest tests/llm/test_client.py::test_model_selection -x` | ❌ Wave 0 |
| LLM-01 | DictaLM Modelfile registration is idempotent (re-run does not fail) | structural | grep `ollama create dictalm3` in `scripts/download_models.sh` (already covered Phase 1) | ✅ |
| LLM-02 | `generate_suggestions` is `AsyncGenerator[SuggestionEvent, None]` and yields TokenEvent + CompleteEvent | contract | `pytest tests/llm/test_engine.py::test_yields_token_then_complete -x` | ❌ Wave 0 |
| LLM-02 | Engine call does NOT block FastAPI event loop (concurrent two calls + WS heartbeat both progress) | behavioral | `pytest tests/llm/test_engine.py::test_no_event_loop_blocking -x` | ❌ Wave 0 |
| LLM-03 | Empty `context_chunks` short-circuits to refusal without calling Ollama | unit | `pytest tests/llm/test_engine.py::test_empty_context_short_circuit -x` | ❌ Wave 0 |
| LLM-03 | Insufficient-context grounded fixture returns `"אין לי מספיק מידע"` | behavioral (mocked Ollama) | `pytest tests/llm/test_engine.py::test_refusal_on_irrelevant_context -x` | ❌ Wave 0 |
| LLM-03 | Live grounding probe — small fixture against real Ollama if `RECEPTRA_LLM_LIVE_TEST=1` set | manual | `RECEPTRA_LLM_LIVE_TEST=1 pytest tests/llm/test_engine_live.py -x -m live` | ❌ Wave 0 (skipped by default) |
| LLM-04 | Stream of valid JSON tokens parses to `SuggestionResponse` cleanly | contract | `pytest tests/llm/test_engine.py::test_parse_valid_stream -x` | ❌ Wave 0 |
| LLM-04 | Markdown-fenced JSON output parses after fence-strip | regression | `pytest tests/llm/test_engine.py::test_parse_strips_markdown_fences -x` | ❌ Wave 0 |
| LLM-04 | Malformed JSON → one retry → success (parse_retry_ok status) | behavioral | `pytest tests/llm/test_engine.py::test_parse_retry_recovers -x` | ❌ Wave 0 |
| LLM-04 | Malformed JSON → retry also fails → LlmErrorEvent + canonical refusal CompleteEvent | chaos | `pytest tests/llm/test_engine.py::test_parse_retry_exhausted -x` | ❌ Wave 0 |
| LLM-05 | TTFT recorded on first non-empty token; absent if no tokens | unit | `pytest tests/llm/test_metrics.py::test_ttft_set_on_first_token -x` | ❌ Wave 0 |
| LLM-05 | SQLite `llm_calls` row written exactly once per `generate_suggestions` invocation | regression | `pytest tests/llm/test_audit.py::test_one_row_per_call -x` | ❌ Wave 0 |
| LLM-05 | Logging failure does NOT crash engine (loguru sink raises → caller still gets CompleteEvent) | chaos | `pytest tests/llm/test_engine.py::test_logging_failure_swallowed -x` | ❌ Wave 0 |
| LLM-06 | `scripts/eval_llm.py --transcript ... --context-file empty_context.json` exits 0 with refusal | smoke | `python scripts/eval_llm.py --transcript "שלום" --context-file fixtures/llm/empty_context.json` | ❌ Wave 0 |
| LLM-06 | Harness import does NOT load `receptra.stt` | regression | `pytest tests/llm/test_harness_isolation.py::test_no_stt_import -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `cd backend && uv run ruff check . && uv run mypy src && uv run pytest tests/llm/ -x`
- **Per wave merge:** `cd backend && uv run pytest tests/` + ruff format check
- **Phase gate:** Full suite green + manual `RECEPTRA_LLM_LIVE_TEST=1` run on a Mac with Ollama running (covers LLM-01 + LLM-03 live behavior). Harness smoke (`scripts/eval_llm.py`) green on all four fixtures.

### Nyquist Validation Dimensions

1. **Structural:** `receptra/llm/__init__.py`, `client.py`, `prompts.py`, `schema.py`, `engine.py`, `metrics.py`, `audit.py` exist; `scripts/eval_llm.py` exists; `fixtures/llm/*.json` (4 files) exist.
2. **Behavioral:** mocked-Ollama tests cover stream → parse → CompleteEvent + refusal + retry paths.
3. **Contract:** pydantic schema validates fixtures; SuggestionEvent discriminator round-trips through `TypeAdapter.dump_json` + `model_validate_json`.
4. **Chaos:** Ollama unreachable → typed `LlmErrorEvent`; malformed JSON exhausted → typed error; logging failure swallowed; concurrent calls don't block each other; harness import doesn't pull in STT.
5. **Regression:** Markdown-fence stripping; PII redaction default-on; one audit row per call; harness STT-independence.

### Wave 0 Gaps

- [ ] `backend/src/receptra/llm/__init__.py` + 6 module skeletons
- [ ] `backend/tests/llm/__init__.py`
- [ ] `backend/tests/llm/conftest.py` — shared `mock_ollama_client` fixture (autouse for `tests/llm/` only, mirroring Phase 2's `_stub_heavy_loaders` pattern)
- [ ] `backend/tests/llm/fixtures/` — canned chunk + canned model-output fixtures
- [ ] `fixtures/llm/policy_returns.json`, `policy_hours.json`, `empty_context.json`, `eval_set.jsonl`
- [ ] `scripts/eval_llm.py`
- [ ] `docs/llm.md` — Phase 3 contract doc parallel to Phase 2's `docs/stt.md`
- [ ] `backend/pyproject.toml` — add `ollama>=0.6.1,<1` to `[project].dependencies`
- [ ] `.env.example` — add `RECEPTRA_LLM_*` keys
- [ ] `backend/src/receptra/config.py` — extend Settings with §6.5 fields
- [ ] `scripts/check_licenses.sh` PY_ALLOW already covers MIT (ollama license) — re-run after pyproject.toml edit to confirm allowlist stays green

## Security Domain

(`security_enforcement` not explicitly disabled in config; section required.)

### Applicable ASVS Categories

| ASVS Category | Applies | Standard control |
|---------------|---------|-----------------|
| V2 Authentication | No | Engine is internal; no public route added in Phase 3 |
| V3 Session Management | No | Stateless per-call |
| V4 Access Control | No | Same as V2 |
| V5 Input Validation | YES | pydantic schema on `SuggestionResponse`; transcript length bound (`len(transcript) ≤ 2000` chars before send to model — DoS guard) |
| V6 Cryptography | YES | sha256 over transcript for audit hash (using `hashlib`, never hand-rolled) |
| V7 Error Handling & Logging | YES | PII default-redact; typed error envelopes; never leak Ollama stack traces to wire |
| V8 Data Protection | YES | Transcripts are PII; audit DB on local volume only; no network egress; same boundary Phase 2 enforced |
| V9 Communication | YES | Ollama HTTP is loopback-only on host; `host.docker.internal` is non-routable from public net |
| V14 Configuration | YES | All LLM params `RECEPTRA_LLM_*` env-driven; defaults safe; no hardcoded secrets |

### Known threat patterns for {ollama + FastAPI + local LLM}

| Pattern | STRIDE | Standard mitigation |
|---------|--------|---------------------|
| Prompt injection via transcript ("ignore previous instructions...") | T (Tampering) | DictaLM 3.0 + low temperature + few-shot grounding makes this hard but NOT immune. Defense: §5.5 hard short-circuit on empty context bypasses model entirely; system prompt is in Hebrew (English injection prompts often misfire); audit log records full message for post-hoc review. **Out of scope for Phase 3 to fully harden — Phase 7 polish revisits.** [VERIFIED industry consensus 2026: prompt injection has no general defense] |
| PII leak via logs | I (Information disclosure) | Default-redact transcript text in loguru sink; audit row stores hash not text; opt-in disable env var documented as PII-boundary-weakening |
| DoS via giant transcript | D (Denial of service) | Bound `len(transcript) ≤ 2000` chars at engine entry; raise `ValueError` before reaching Ollama |
| DoS via giant context | D | Bound `len(context_chunks) ≤ 10` and `sum(len(c.text)) ≤ 12000` chars; trims downstream to fit num_ctx=8192 |
| Malformed JSON crashing pipeline | T | Bounded retry + canonical refusal fallback (§6.2 step 7); LlmErrorEvent envelope (typed) |
| Ollama process unreachable | D | 30 s timeout + typed `ollama_unreachable` error; engine never blocks indefinitely |
| Audit DB tampering | T | Local-only file under `data/`; mounted with `:rw` to one container; documented in `docs/llm.md` Security section |

## Open Decisions

Items the planner should resolve (or defer) before Phase 3 executes.

### OPEN-LLM-1: Few-shot strategy — in system prompt vs alternating turns
**Recommendation:** Alternating user/assistant turns (§5.4 spec). Cleaner ChatML rendering; DictaLM 3.0's chat template handles them natively; lower risk of role confusion.
**Alternative:** Bake examples into system prompt as text. More compact but DictaLM may misinterpret system-prompt examples as system-level constraints.
**Lock:** alternating turns. No user input needed.

### OPEN-LLM-2: System prompt language default — Hebrew vs English
**Recommendation:** Hebrew default; English variant behind `RECEPTRA_LLM_SYSTEM_PROMPT_LANG=en` env var.
**Risk:** No published Hebrew prompt-engineering benchmarks; we trust DictaLM 3.0 follows native Hebrew instructions better than English ones.
**What planner should ask user:** confirm default = Hebrew, OR ask Phase 7 to A/B test.
**Lock recommendation:** Hebrew default; Phase 7 A/B.

### OPEN-LLM-3: `format=schema` enforcement on retry path
**Recommendation:** Use `format="json"` (loose JSON mode) on retry, NOT `format=Suggestion.model_json_schema()`. Ollama issues #14440/#15260 cast doubt on schema enforcement reliability. Loose JSON + Pydantic post-parse is a known-good 2026 pattern.
**Risk:** A future Ollama bugfix may make `format=schema` reliable enough to drop the retry; document this as a Phase 7 / post-v1 simplification candidate.
**Lock:** loose JSON + post-parse for v1.

### OPEN-LLM-4: Logprobs in audit row
**Recommendation:** YES — pass `logprobs=True` and store `mean_logprob` per call for Phase 7 confidence-calibration analysis. Cost is one extra column in the SQLite row + tiny CPU overhead.
**Alternative:** Skip — keep audit lean, revisit in Phase 7.
**Lock:** YES, store. Cheap to add now, painful to backfill later.

### OPEN-LLM-5: CLI harness as `uv run` script vs standalone Python
**Recommendation:** `uv run --project backend python scripts/eval_llm.py` — uses backend's locked deps, no separate venv to maintain.
**Alternative:** Standalone tool at repo root with its own pyproject.toml. Heavier; out of scope for v1.
**Lock:** `uv run --project backend`. Document in `docs/llm.md`.

### OPEN-LLM-6: Live test gating
**Recommendation:** Default-skip live Ollama tests via pytest marker `@pytest.mark.live`. Run only when `RECEPTRA_LLM_LIVE_TEST=1` is set. Ensures CI on ubuntu-latest (no host Ollama) stays green; Mac dev can run live suite manually.
**Lock:** opt-in marker.

### OPEN-LLM-7: Where to put `Suggestion` schema for cross-phase use
**Recommendation:** `receptra.llm.schema` is the canonical home (Phase 3). Phase 4 RAG re-exports `ChunkRef` from `receptra.rag.types`. Phase 5 hot path imports both — no duplication. Phase 6 frontend duplicates the type in TypeScript via codegen (Phase 6's concern; not Phase 3's).
**Lock:** Phase 3 owns `Suggestion`/`SuggestionResponse`/`SuggestionEvent`.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Hebrew system prompt outperforms English for DictaLM 3.0 | §5.1 | Phase 7 A/B may invert this; `RECEPTRA_LLM_SYSTEM_PROMPT_LANG` switch makes it cheap to flip. Low risk to Phase 3 exit. |
| A2 | Self-reported confidence is good enough for v1 UI signal | §4.2, §5.6 | UI may sort suggestions wrongly; Phase 7 logprob analysis catches drift. Low risk. |
| A3 | DictaLM 3.0 Q4_K_M fits + runs <500 ms TTFT on M2 16 GB | §8 | If TTFT exceeds budget, fallback is Qwen 2.5 7B (lighter). Phase 7 latency baseline is the true verdict. |
| A4 | One bounded retry on parse failure is sufficient | §6.2 | If DictaLM has a JSON-format weakness we don't see in fixtures, we'll see elevated `parse_error` rate in audit; Phase 7 prompt-tune addresses it. |
| A5 | DictaLM 3.0's tokenizer.chat_template metadata is embedded in the GGUF (so Ollama auto-detects) | §3.1, §3.2 | If absent, Modelfile needs an explicit `TEMPLATE` block. Phase 1 already shipped without explicit TEMPLATE; if Phase 3 hits a chat-template miss, add `TEMPLATE """{{ if .System }}<|im_start|>system\n{{ .System }}<|im_end|>\n{{ end }}<|im_start|>user\n{{ .Prompt }}<|im_end|>\n<|im_start|>assistant\n"""` to DictaLM3.Modelfile. Recoverable. |
| A6 | `ollama` Python package versions ≥0.6.1 maintain backward-compat for `AsyncClient.chat(stream=True)` chunk shape | §1.2-1.3 | A 1.0 release could break us; pin upper bound `<1` in pyproject.toml. |
| A7 | Customer transcripts ≤2000 chars suffice for v1 | §6.5 (length guard) | If real calls produce longer transcripts, raise the bound and re-evaluate context-window math. |
| A8 | Hebrew customer-service phrasing in our few-shot examples represents v1 use cases | §5.4 | Phase 7 review by a Hebrew speaker (DEMO-02) catches voice/tone misalignment; v1 ships with placeholders. |

**Conclusion on assumptions:** None block Phase 3. A5 is the highest-impact assumption; it's verified by chat_template.jinja existence on HF but Ollama's GGUF-metadata extraction is one upstream-tool removed. Plan can include a smoke-test step: after `ollama create dictalm3`, run `ollama show dictalm3 --modelfile` and grep for ChatML markers. If absent, fail fast and add explicit TEMPLATE.

## Sources

### Primary (HIGH confidence)
- [Ollama Python README + AsyncClient + streaming + structured outputs](https://github.com/ollama/ollama-python) (via Context7 `/ollama/ollama-python`)
- [Ollama API docs — /api/chat + structured outputs](https://docs.ollama.com/api/chat) (via Context7 `/websites/ollama`)
- [Ollama structured outputs blog post](https://ollama.com/blog/structured-outputs)
- [DictaLM-3.0-Nemotron-12B-Instruct chat_template.jinja](https://huggingface.co/dicta-il/DictaLM-3.0-Nemotron-12B-Instruct/raw/main/chat_template.jinja) — direct fetch verified ChatML format
- [DictaLM-3.0-Nemotron-12B-Instruct tokenizer_config.json](https://huggingface.co/dicta-il/DictaLM-3.0-Nemotron-12B-Instruct/raw/main/tokenizer_config.json) — special token IDs
- [DictaLM-3.0-Nemotron-12B-Instruct-GGUF model card](https://huggingface.co/dicta-il/DictaLM-3.0-Nemotron-12B-Instruct-GGUF) — quant sizes
- [Hugging Face Ollama integration docs](https://huggingface.co/docs/hub/ollama) — GGUF chat-template auto-detection
- [Phase 1 RESEARCH.md](.planning/phases/01-foundation/01-RESEARCH.md) — Modelfile + Q4 strategy + Ollama-on-host decision
- [pypi.org/project/ollama](https://pypi.org/project/ollama/) — version 0.6.1 verified
- [github.com/ollama/ollama-python releases](https://github.com/ollama/ollama-python/releases) — logprobs added 0.6.1

### Secondary (MEDIUM confidence)
- [github.com/ollama/ollama issue #14440](https://github.com/ollama/ollama/issues/14440) — schema-enforcement-during-streaming caveat
- [github.com/ollama/ollama issue #15260](https://github.com/ollama/ollama/issues/15260) — `think=false` breaks `format`
- [dev.to/busycaesar — Ollama 0.5 Is Here: Generate Structured Outputs](https://dev.to/busycaesar/structured-response-using-ollama-2i73) — version-introduction confirmation
- [aiamastery.substack.com — Lesson 25: Advanced Prompting for RAG](https://aiamastery.substack.com/p/lesson-25-advanced-prompting-for) — grounding refusal patterns
- [apxml.com — Structuring Prompts for RAG Systems](https://apxml.com/courses/getting-started-rag/chapter-4-rag-generation-augmentation/structuring-rag-prompts) — explicit context delimiters

### Tertiary (LOW confidence — verify at execution time)
- DictaLM 3.0 specifically follows Hebrew instructions better than English (industry consensus on Hebrew-native models; not benchmarked in this research) — A1
- M2 16 GB DictaLM 12B Q4 TTFT < 500 ms target (Phase 7 latency baseline is the true verdict) — A3
- Customer transcripts ≤2000 chars is adequate for v1 use cases (typical agent-call utterances are short, but no real-call data yet) — A7

## Metadata

**Confidence breakdown:**
- Ollama Python client API: HIGH — verified via Context7 + PyPI
- DictaLM 3.0 chat template: HIGH — fetched chat_template.jinja directly from HF
- Streaming + structured outputs interaction: HIGH — multiple upstream issues confirm caveat
- Hebrew prompt template: MEDIUM — written from scratch by this research; Phase 7 will tune
- TTFT instrumentation pattern: HIGH — wall-clock measurement is universal
- CLI harness spec: HIGH — mirrors Phase 2's `scripts/eval_wer.py` pattern

**Research date:** 2026-04-25
**Valid until:** 2026-05-25 (30 days — Ollama Python API and DictaLM 3.0 are stable; re-verify Ollama version before Phase 3 execution if >30 days elapse, since structured-outputs behavior is actively evolving)
