"""BGE-M3 embedder via Ollama (RAG-01).

1024-dim L2-normalized dense vectors for Hebrew + multilingual text.
Pattern mirrors receptra.llm.client (Plan 03-03): typed errors,
fail-fast classmethod, no global state, no logging beyond fail-fast init.

Plan 04-05 lifespan calls ``BgeM3Embedder.create_and_verify()`` once at
startup; consumers (Plan 04-04 ingest + retriever) hold the singleton on
``app.state.embedder``.

Locks (RESEARCH §BGE-M3 Pattern + Plan 04-01 settings):
- ``MODEL = "bge-m3"`` — Ollama model tag, pulled by ``make models-bge``.
- ``DIM = 1024`` — BGE-M3 model card publishes 1024-dim dense output.
- ``_KEEP_ALIVE = "5m"`` — RESEARCH §Cluster 2: not -1; amortizes
  intra-job + query-session calls without parking VRAM forever (BGE-M3 is
  ~1.2 GB so cold-start is cheap).
- Default ``batch_size`` falls back to ``settings.rag_embed_batch_size``
  (16) per Plan 04-01 lock — adjust only if a Wave-0 spike pushes higher.
- Uses ``client.embed(...)`` (current API) NOT ``client.embeddings(...)``
  (deprecated in ollama 0.6.x — RESEARCH §Cluster 2 explicit lock).
"""
from __future__ import annotations

from collections.abc import Sequence

from ollama import AsyncClient

from receptra.config import settings
from receptra.rag.errors import RagInitError


class BgeM3Embedder:
    """BGE-M3 (1024-dim, cosine-normalized) embedder backed by Ollama."""

    DIM: int = 1024
    MODEL: str = "bge-m3"
    # RESEARCH §Cluster 2: not -1; amortizes intra-job calls without
    # parking VRAM forever. Plan 04-04 ingest + Plan 04-05 query both run
    # within this 5-minute window in normal use.
    _KEEP_ALIVE: str = "5m"

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    @classmethod
    async def create_and_verify(cls) -> BgeM3Embedder:
        """Construct + fail-fast if bge-m3 is not pulled.

        Plan 04-05 lifespan calls this; failure raises ``RagInitError``
        with actionable detail ("run: make models-bge") so the FastAPI
        startup banner tells the developer how to recover (T-04-03 reg
        item: model_missing → operator runs the documented command).
        """
        client = AsyncClient(host=settings.ollama_host)
        try:
            await client.show(cls.MODEL)
        except Exception as e:
            raise RagInitError(
                code="model_missing",
                detail=(
                    f"Ollama model {cls.MODEL!r} not available. "
                    "Run: make models-bge"
                ),
            ) from e
        return cls(client)

    async def embed_one(self, text: str) -> list[float]:
        """Embed a single text. Returns 1024 floats."""
        resp = await self._client.embed(
            model=self.MODEL,
            input=text,
            keep_alive=self._KEEP_ALIVE,
        )
        return list(resp.embeddings[0])

    async def embed_batch(
        self,
        texts: Sequence[str],
        batch_size: int | None = None,
    ) -> list[list[float]]:
        """Embed a sequence of texts in batches.

        Args:
            texts: input strings (any Sequence[str]).
            batch_size: chunk size; defaults to
                ``settings.rag_embed_batch_size`` (16).

        Returns:
            One 1024-float list per input, in input order. Ollama processes
            the input list as a true batch (RESEARCH §Cluster 2 verified).
        """
        bs = batch_size if batch_size is not None else settings.rag_embed_batch_size
        out: list[list[float]] = []
        for i in range(0, len(texts), bs):
            batch = list(texts[i : i + bs])
            resp = await self._client.embed(
                model=self.MODEL,
                input=batch,
                keep_alive=self._KEEP_ALIVE,
            )
            out.extend(list(v) for v in resp.embeddings)
        return out


__all__ = ["BgeM3Embedder"]
