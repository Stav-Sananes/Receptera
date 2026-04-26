"""Mocked unit tests for receptra.rag.embeddings (RAG-01).

All tests run offline against an injected fake ``AsyncClient`` — no real
Ollama process is touched. Live round-trip lives in
``test_embeddings_live.py`` and self-skips on CI.

Mocking strategy (Plan 03-05 lock):
- Patch the ``AsyncClient`` symbol *imported into* ``receptra.rag.embeddings``
  rather than the source module — string-path patches break under full-suite
  alphabetical ordering once tests/llm/test_client.py mutates sys.modules.
- Patch ``rag_embed_batch_size`` on the shared ``settings`` singleton via
  ``monkeypatch.setattr(receptra_settings, ...)``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, cast

import httpx
import pytest

from receptra.config import settings as receptra_settings
from receptra.rag.errors import RagInitError

if TYPE_CHECKING:
    from receptra.rag.embeddings import BgeM3Embedder


class _FakeEmbedResponse:
    """Mimics ``ollama._types.EmbedResponse`` (only the ``.embeddings`` attr)."""

    def __init__(self, embeddings: list[list[float]]) -> None:
        self.embeddings = embeddings


class _FakeAsyncClient:
    """Test double for ``ollama.AsyncClient``.

    Records constructor kwargs + every ``embed`` / ``show`` call so tests can
    assert the wrapper passes the expected arguments verbatim.
    """

    last_init_kwargs: ClassVar[dict[str, Any]] = {}

    def __init__(self, **kwargs: Any) -> None:
        # Capture init kwargs (host=...) for assertion in dedicated tests.
        type(self).last_init_kwargs = dict(kwargs)
        self.show_calls: list[str] = []
        self.embed_calls: list[dict[str, Any]] = []
        self._show_should_raise: Exception | None = None
        self._embed_responses: list[list[list[float]]] = []
        self._embed_should_raise: Exception | None = None

    # --- Configurable behaviors ----------------------------------------
    def queue_embed_response(self, vectors: list[list[float]]) -> None:
        self._embed_responses.append(vectors)

    def make_show_raise(self, exc: Exception) -> None:
        self._show_should_raise = exc

    def make_embed_raise(self, exc: Exception) -> None:
        self._embed_should_raise = exc

    # --- ollama.AsyncClient surface ------------------------------------
    async def show(self, model: str) -> Any:
        self.show_calls.append(model)
        if self._show_should_raise is not None:
            raise self._show_should_raise
        return {"model": model}

    async def embed(self, **kwargs: Any) -> _FakeEmbedResponse:
        self.embed_calls.append(kwargs)
        if self._embed_should_raise is not None:
            raise self._embed_should_raise
        if not self._embed_responses:
            # Default: return a single zero vector of the input shape.
            inp: Any = kwargs.get("input")
            n = 1 if isinstance(inp, str) or inp is None else len(list(inp))
            return _FakeEmbedResponse([[0.0] * 1024 for _ in range(n)])
        vectors = self._embed_responses.pop(0)
        return _FakeEmbedResponse(vectors)


@pytest.fixture
def fake_async_client_factory(monkeypatch: pytest.MonkeyPatch) -> type[_FakeAsyncClient]:
    """Patch ``AsyncClient`` symbol imported into receptra.rag.embeddings.

    Returns the fake class so a test can pre-configure responses BEFORE
    ``BgeM3Embedder.create_and_verify()`` constructs the singleton.
    """
    import receptra.rag.embeddings as emb_mod

    monkeypatch.setattr(emb_mod, "AsyncClient", _FakeAsyncClient)
    return _FakeAsyncClient


def _fake_client(embedder: BgeM3Embedder) -> _FakeAsyncClient:
    """Cast embedder._client to the test fake.

    Mypy strict treats ``BgeM3Embedder._client`` as ``ollama.AsyncClient``.
    Tests inject ``_FakeAsyncClient`` via monkeypatch so the runtime type
    is the fake; this cast is a runtime-asserted compile-time hint.
    """
    assert isinstance(embedder._client, _FakeAsyncClient)
    return cast(_FakeAsyncClient, embedder._client)


# ==========================================================================
# Test class
# ==========================================================================


class TestBgeM3Embedder:
    """8 mocked unit tests for the BGE-M3 wrapper (RAG-01)."""

    # --- Test 1 -----------------------------------------------------------
    def test_class_constants(self) -> None:
        """DIM=1024 + MODEL='bge-m3' are pinned constants Plan 04-04/05 import."""
        from receptra.rag.embeddings import BgeM3Embedder

        assert BgeM3Embedder.DIM == 1024
        assert BgeM3Embedder.MODEL == "bge-m3"

    # --- Test 2 -----------------------------------------------------------
    @pytest.mark.asyncio
    async def test_create_and_verify_success(
        self, fake_async_client_factory: type[_FakeAsyncClient]
    ) -> None:
        """Happy path: ``show('bge-m3')`` succeeds → returns instance with _client."""
        from receptra.rag.embeddings import BgeM3Embedder

        embedder = await BgeM3Embedder.create_and_verify()
        assert embedder is not None
        assert isinstance(embedder, BgeM3Embedder)
        assert hasattr(embedder, "_client")
        client = _fake_client(embedder)
        assert client.show_calls == ["bge-m3"]

    # --- Test 3 -----------------------------------------------------------
    @pytest.mark.asyncio
    async def test_create_and_verify_raises_model_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``show`` raises → RagInitError(code='model_missing'), detail mentions make models-bge."""
        import receptra.rag.embeddings as emb_mod

        class _RaisingClient(_FakeAsyncClient):
            def __init__(self, **kwargs: Any) -> None:
                super().__init__(**kwargs)
                self.make_show_raise(Exception("not found"))

        monkeypatch.setattr(emb_mod, "AsyncClient", _RaisingClient)

        from receptra.rag.embeddings import BgeM3Embedder

        with pytest.raises(RagInitError) as exc_info:
            await BgeM3Embedder.create_and_verify()
        assert exc_info.value.code == "model_missing"
        assert "make models-bge" in exc_info.value.detail

    # --- Test 4 -----------------------------------------------------------
    @pytest.mark.asyncio
    async def test_embed_one_returns_1024_floats(
        self, fake_async_client_factory: type[_FakeAsyncClient]
    ) -> None:
        """Returns 1024 floats; passes model+input+keep_alive verbatim to ``embed``."""
        from receptra.rag.embeddings import BgeM3Embedder

        embedder = await BgeM3Embedder.create_and_verify()
        client = _fake_client(embedder)
        client.queue_embed_response([[0.1] * 1024])

        v = await embedder.embed_one("שלום")
        assert isinstance(v, list)
        assert len(v) == 1024
        assert all(isinstance(x, float) for x in v)

        # Verify call kwargs verbatim — guards T-04-03-01 (no embeddings() typo).
        call = client.embed_calls[-1]
        assert call["model"] == "bge-m3"
        assert call["input"] == "שלום"
        assert call["keep_alive"] == "5m"

    # --- Test 5 -----------------------------------------------------------
    @pytest.mark.asyncio
    async def test_embed_batch_chunks_by_batch_size(
        self, fake_async_client_factory: type[_FakeAsyncClient]
    ) -> None:
        """batch_size=2, 5 inputs → 3 calls (2,2,1) and 5 vectors in input order."""
        from receptra.rag.embeddings import BgeM3Embedder

        embedder = await BgeM3Embedder.create_and_verify()
        client = _fake_client(embedder)
        # Pre-queue three responses (sizes 2,2,1).
        client.queue_embed_response([[1.0] * 1024, [2.0] * 1024])
        client.queue_embed_response([[3.0] * 1024, [4.0] * 1024])
        client.queue_embed_response([[5.0] * 1024])

        out = await embedder.embed_batch(["a", "b", "c", "d", "e"], batch_size=2)
        assert len(out) == 5
        assert all(len(v) == 1024 for v in out)
        assert len(client.embed_calls) == 3

        # Verify each batch call sent the right slice (input order preserved).
        assert client.embed_calls[0]["input"] == ["a", "b"]
        assert client.embed_calls[1]["input"] == ["c", "d"]
        assert client.embed_calls[2]["input"] == ["e"]

    # --- Test 6 -----------------------------------------------------------
    @pytest.mark.asyncio
    async def test_embed_batch_uses_settings_default(
        self,
        fake_async_client_factory: type[_FakeAsyncClient],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """No batch_size kwarg → defaults to settings.rag_embed_batch_size."""
        monkeypatch.setattr(receptra_settings, "rag_embed_batch_size", 4)

        from receptra.rag.embeddings import BgeM3Embedder

        embedder = await BgeM3Embedder.create_and_verify()
        client = _fake_client(embedder)
        # 7 inputs at batch_size=4 → 2 batches: 4 + 3
        client.queue_embed_response([[0.0] * 1024 for _ in range(4)])
        client.queue_embed_response([[0.0] * 1024 for _ in range(3)])

        out = await embedder.embed_batch(["a", "b", "c", "d", "e", "f", "g"])
        assert len(out) == 7
        assert len(client.embed_calls) == 2
        assert len(client.embed_calls[0]["input"]) == 4
        assert len(client.embed_calls[1]["input"]) == 3

    # --- Test 7 -----------------------------------------------------------
    @pytest.mark.asyncio
    async def test_embed_batch_preserves_order(
        self, fake_async_client_factory: type[_FakeAsyncClient]
    ) -> None:
        """Output ordering matches input ordering across batch boundaries."""
        from receptra.rag.embeddings import BgeM3Embedder

        embedder = await BgeM3Embedder.create_and_verify()
        client = _fake_client(embedder)
        # Sentinel: vector[0] encodes the input position.
        client.queue_embed_response([
            [float(i)] + [0.0] * 1023 for i in (0, 1)
        ])
        client.queue_embed_response([
            [float(i)] + [0.0] * 1023 for i in (2, 3)
        ])
        client.queue_embed_response([
            [float(i)] + [0.0] * 1023 for i in (4,)
        ])

        out = await embedder.embed_batch(["a", "b", "c", "d", "e"], batch_size=2)
        # First float of each output vector = input position
        positions = [v[0] for v in out]
        assert positions == [0.0, 1.0, 2.0, 3.0, 4.0]

    # --- Test 8 -----------------------------------------------------------
    @pytest.mark.asyncio
    async def test_embed_one_propagates_httpx_errors(
        self, fake_async_client_factory: type[_FakeAsyncClient]
    ) -> None:
        """httpx.ConnectError is NOT swallowed — Plan 04-05 routes layer wraps to 503."""
        from receptra.rag.embeddings import BgeM3Embedder

        embedder = await BgeM3Embedder.create_and_verify()
        client = _fake_client(embedder)
        client.make_embed_raise(httpx.ConnectError("ollama down"))

        with pytest.raises(httpx.ConnectError):
            await embedder.embed_one("שלום")
