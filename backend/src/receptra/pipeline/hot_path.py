"""Hot-path suggest callback factory (Phase 5 INT-01 + INT-02 + INT-04).

``make_suggest_fn`` builds a per-connection ``SuggestFn`` closure that:

1. Retrieves top-K chunks from ChromaDB using the transcript as query
   (INT-04: skip gracefully if embedder or collection is None, or if
   retrieval raises — chunks falls back to [] → canonical refusal).

2. Streams ``generate_suggestions(transcript, chunks)`` and forwards each
   ``SuggestionEvent`` to the WebSocket as the corresponding pipeline event
   (``SuggestionToken``, ``SuggestionComplete``, ``SuggestionError``).

3. Records ``rag_latency_ms`` and ``e2e_latency_ms`` in every
   ``SuggestionComplete`` for INT-03 latency instrumentation.

4. Writes one ``PipelineRunRecord`` to the unified audit log (INT-05).

INT-04 graceful-degradation contract:
- embedder is None → skip retrieve → chunks=[]
- collection is None → same
- retrieval raises → SuggestionError("rag_unavailable", ...) + chunks=[]
- LLM errors → SuggestionError(event.code, ...)
- Any send failure (client disconnected) → swallowed; loop ends naturally

``SuggestFn`` signature: ``async (transcript, t_speech_end_ms, utterance_id) → None``.
``t_speech_end_ms`` is the monotonic timestamp (ms) when VAD detected speech end.
``utterance_id`` is the per-utterance UUID used to join with stt_utterances.
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from loguru import logger

from receptra.llm.engine import generate_suggestions
from receptra.llm.schema import CompleteEvent, LlmErrorEvent, TokenEvent
from receptra.pipeline.events import SuggestionComplete, SuggestionError, SuggestionToken

if TYPE_CHECKING:
    from chromadb.api.models.Collection import Collection

    from receptra.llm.schema import ChunkRef
    from receptra.rag.embeddings import BgeM3Embedder

# Import retrieve at module level (not TYPE_CHECKING) so patch() in tests works.
from receptra.rag.retriever import retrieve

SuggestFn = Callable[[str, int, str], Awaitable[None]]
"""Async callable: ``(transcript, t_speech_end_ms, utterance_id) → None``."""


def _now_ms() -> int:
    """Monotonic millisecond timestamp."""
    return int(time.monotonic() * 1000)


def make_suggest_fn(
    ws: object,  # FastAPI WebSocket; typed as object to avoid heavy import at module level
    embedder: BgeM3Embedder | None,
    collection: Collection | None,
) -> SuggestFn:
    """Build a per-connection suggest callback.

    The returned callable is intended to be awaited inline inside
    ``run_utterance_loop`` after each ``FinalTranscript`` is sent —
    not as a background task. This serialises neatly on a single WS
    connection and avoids concurrent audit writes on the same utterance_id.

    Args:
        ws: Accepted FastAPI WebSocket; ``send_json`` must be callable.
        embedder: BgeM3Embedder singleton from app.state; may be None on
            degradation (INT-04).
        collection: ChromaDB Collection from app.state; may be None (INT-04).

    Returns:
        ``SuggestFn`` async callable.
    """

    async def _suggest(
        transcript: str,
        t_speech_end_ms: int,
        utterance_id: str,
    ) -> None:
        from receptra.config import settings
        from receptra.pipeline.audit import PipelineRunRecord, insert_pipeline_run
        from receptra.stt.metrics import utc_now_iso

        t_rag_start = _now_ms()
        chunks: list[ChunkRef] = []
        rag_degraded = False

        # --- RAG retrieval (INT-04 degradation) ---
        if embedder is not None and collection is not None:
            try:
                chunks = await retrieve(
                    query=transcript,
                    embedder=embedder,
                    collection=collection,
                )
            except Exception as exc:
                rag_degraded = True
                logger.bind(event="pipeline.rag_error").warning(
                    {"msg": "RAG retrieval failed — degrading to empty chunks", "err": str(exc)}
                )
                with contextlib.suppress(Exception):
                    await ws.send_json(  # type: ignore[attr-defined]
                        SuggestionError(
                            code="rag_unavailable",
                            detail=f"RAG retrieval failed: {exc}",
                        ).model_dump()
                    )
        else:
            logger.bind(event="pipeline.rag_skip").debug(
                {"msg": "embedder or collection unavailable — skipping RAG (INT-04)"}
            )

        rag_latency_ms = _now_ms() - t_rag_start

        # --- LLM generation (empty chunks → canonical refusal via engine short-circuit) ---
        llm_ttft_ms: int | None = None
        llm_total_ms: int | None = None
        n_suggestions = 0
        llm_status = "ok"
        e2e_latency_ms: int | None = None

        try:
            async for event in generate_suggestions(transcript, chunks):
                if isinstance(event, TokenEvent):
                    try:
                        await ws.send_json(  # type: ignore[attr-defined]
                            SuggestionToken(delta=event.delta).model_dump()
                        )
                    except Exception:
                        return  # client disconnected mid-stream

                elif isinstance(event, CompleteEvent):
                    e2e_latency_ms = _now_ms() - t_speech_end_ms
                    llm_ttft_ms = event.ttft_ms
                    llm_total_ms = event.total_ms
                    n_suggestions = len(event.suggestions)
                    try:
                        await ws.send_json(  # type: ignore[attr-defined]
                            SuggestionComplete(
                                suggestions=list(event.suggestions),
                                ttft_ms=event.ttft_ms,
                                total_ms=event.total_ms,
                                model=event.model,
                                rag_latency_ms=rag_latency_ms,
                                e2e_latency_ms=e2e_latency_ms,
                            ).model_dump()
                        )
                    except Exception:
                        return  # client disconnected

                elif isinstance(event, LlmErrorEvent):
                    llm_status = event.code
                    try:
                        await ws.send_json(  # type: ignore[attr-defined]
                            SuggestionError(
                                code=event.code,
                                detail=event.detail,
                            ).model_dump()
                        )
                    except Exception:
                        return

        except Exception as exc:
            llm_status = "pipeline_error"
            logger.bind(event="pipeline.error").error(
                {"msg": "unexpected error in suggest pipeline", "err": str(exc)}
            )
            with contextlib.suppress(Exception):
                await ws.send_json(  # type: ignore[attr-defined]
                    SuggestionError(code="pipeline_error", detail=str(exc)).model_dump()
                )

        # --- INT-05: Unified audit log ---
        final_status = (
            "rag_degraded" if rag_degraded
            else llm_status if llm_status != "ok"
            else "ok"
        )
        record = PipelineRunRecord(
            utterance_id=utterance_id,
            ts_utc=utc_now_iso(),
            stt_latency_ms=0,  # passed by caller; not available in this closure
            rag_latency_ms=rag_latency_ms,
            llm_ttft_ms=llm_ttft_ms,
            llm_total_ms=llm_total_ms,
            n_chunks=len(chunks),
            n_suggestions=n_suggestions,
            status=final_status,
            e2e_latency_ms=e2e_latency_ms,
        )
        try:
            insert_pipeline_run(settings.audit_db_path, record)
        except Exception as exc:
            logger.bind(event="pipeline.audit_failed").error(
                {"utterance_id": utterance_id, "err": str(exc)}
            )

    return _suggest


__all__ = ["SuggestFn", "make_suggest_fn"]
