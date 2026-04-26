"""Mocked unit tests for receptra.rag.vector_store (RAG-02).

All tests run offline against an injected fake ``chromadb`` module — no real
ChromaDB container is contacted. Cosine-distance pinning is the load-bearing
contract here (T-04-03-04 mitigation).
"""
from __future__ import annotations

from typing import Any, ClassVar
from unittest.mock import MagicMock

import pytest

from receptra.rag.errors import RagInitError

# ==========================================================================
# Fakes
# ==========================================================================


class _FakeHttpClient:
    """Test double for ``chromadb.HttpClient`` (sync surface)."""

    last_init_kwargs: ClassVar[dict[str, Any]] = {}

    def __init__(self, **kwargs: Any) -> None:
        type(self).last_init_kwargs = dict(kwargs)
        self.heartbeat_calls = 0
        self.get_or_create_calls: list[dict[str, Any]] = []
        self._heartbeat_should_raise: Exception | None = None
        self._collection_sentinel: Any = None

    def configure_heartbeat_raise(self, exc: Exception) -> None:
        self._heartbeat_should_raise = exc

    def configure_collection(self, sentinel: Any) -> None:
        self._collection_sentinel = sentinel

    def heartbeat(self) -> int:
        self.heartbeat_calls += 1
        if self._heartbeat_should_raise is not None:
            raise self._heartbeat_should_raise
        return 1234567890

    def get_or_create_collection(self, **kwargs: Any) -> Any:
        self.get_or_create_calls.append(kwargs)
        return self._collection_sentinel


class _FakeChromadbModule:
    """Container for ``HttpClient`` symbol + a registry for the latest instance."""

    last_instance: ClassVar[_FakeHttpClient | None] = None

    @classmethod
    def reset(cls) -> None:
        cls.last_instance = None

    @classmethod
    def HttpClient(cls, **kwargs: Any) -> _FakeHttpClient:  # noqa: N802
        # Mirror the chromadb.HttpClient name (PascalCase intentional).
        inst = _FakeHttpClient(**kwargs)
        cls.last_instance = inst
        return inst


@pytest.fixture
def fake_chromadb(monkeypatch: pytest.MonkeyPatch) -> type[_FakeChromadbModule]:
    """Patch the ``chromadb`` symbol imported into receptra.rag.vector_store."""
    import receptra.rag.vector_store as vs_mod

    _FakeChromadbModule.reset()
    monkeypatch.setattr(vs_mod, "chromadb", _FakeChromadbModule)
    return _FakeChromadbModule


def _install_http_client_with_collection(
    monkeypatch: pytest.MonkeyPatch,
    fake_chromadb: type[_FakeChromadbModule],
    sentinel: Any,
) -> None:
    """Replace HttpClient so each new instance returns ``sentinel`` from get_or_create."""
    def factory(**kwargs: Any) -> _FakeHttpClient:
        inst = _FakeHttpClient(**kwargs)
        inst.configure_collection(sentinel)
        fake_chromadb.last_instance = inst
        return inst

    monkeypatch.setattr(
        fake_chromadb,
        "HttpClient",
        classmethod(lambda _cls, **kw: factory(**kw)),
    )


def _install_http_client_with_heartbeat_failure(
    monkeypatch: pytest.MonkeyPatch,
    fake_chromadb: type[_FakeChromadbModule],
    exc: Exception,
) -> None:
    """Replace HttpClient so each instance raises ``exc`` from heartbeat()."""
    def factory(**kwargs: Any) -> _FakeHttpClient:
        inst = _FakeHttpClient(**kwargs)
        inst.configure_heartbeat_raise(exc)
        fake_chromadb.last_instance = inst
        return inst

    monkeypatch.setattr(
        fake_chromadb,
        "HttpClient",
        classmethod(lambda _cls, **kw: factory(**kw)),
    )


# ==========================================================================
# Tests
# ==========================================================================


def test_collection_name_constant() -> None:
    """Pin COLLECTION_NAME — Plan 04-04 ingest imports this constant."""
    from receptra.rag.vector_store import COLLECTION_NAME

    assert COLLECTION_NAME == "receptra_kb"


def test_parse_chroma_host_compose() -> None:
    """Compose-style URL: 'http://chromadb:8000' → ('chromadb', 8000)."""
    from receptra.rag.vector_store import parse_chroma_host

    assert parse_chroma_host("http://chromadb:8000") == ("chromadb", 8000)


def test_parse_chroma_host_localhost() -> None:
    """Localhost URL: 'http://localhost:8000' → ('localhost', 8000)."""
    from receptra.rag.vector_store import parse_chroma_host

    assert parse_chroma_host("http://localhost:8000") == ("localhost", 8000)


def test_parse_chroma_host_default_port() -> None:
    """No explicit port → default 8000."""
    from receptra.rag.vector_store import parse_chroma_host

    assert parse_chroma_host("http://chromadb") == ("chromadb", 8000)


def test_parse_chroma_host_invalid() -> None:
    """Empty / malformed input → RagInitError(chroma_unreachable)."""
    from receptra.rag.vector_store import parse_chroma_host

    with pytest.raises(RagInitError) as exc_info:
        parse_chroma_host("")
    assert exc_info.value.code == "chroma_unreachable"

    with pytest.raises(RagInitError) as exc_info_2:
        parse_chroma_host("not-a-url")
    assert exc_info_2.value.code == "chroma_unreachable"


def test_open_collection_happy_path(
    fake_chromadb: type[_FakeChromadbModule],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Heartbeat OK → returns collection from get_or_create with cosine metadata."""
    from receptra.config import settings as receptra_settings
    monkeypatch.setattr(receptra_settings, "chroma_host", "http://chromadb:8000")

    sentinel = MagicMock(name="receptra_kb_collection")
    _install_http_client_with_collection(monkeypatch, fake_chromadb, sentinel)

    from receptra.rag.vector_store import open_collection

    result = open_collection()
    assert result is sentinel

    inst = fake_chromadb.last_instance
    assert inst is not None
    assert inst.heartbeat_calls == 1
    # HttpClient constructed with parsed host + port
    assert _FakeHttpClient.last_init_kwargs == {"host": "chromadb", "port": 8000}
    # get_or_create_collection called with name + cosine metadata, verbatim
    assert len(inst.get_or_create_calls) == 1
    call = inst.get_or_create_calls[0]
    assert call == {"name": "receptra_kb", "metadata": {"hnsw:space": "cosine"}}


def test_open_collection_unreachable(
    fake_chromadb: type[_FakeChromadbModule],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Heartbeat raises → RagInitError(chroma_unreachable) with host:port detail."""
    from receptra.config import settings as receptra_settings
    monkeypatch.setattr(receptra_settings, "chroma_host", "http://chromadb:8000")

    _install_http_client_with_heartbeat_failure(
        monkeypatch, fake_chromadb, Exception("connection refused")
    )

    from receptra.rag.vector_store import open_collection

    with pytest.raises(RagInitError) as exc_info:
        open_collection()
    assert exc_info.value.code == "chroma_unreachable"
    # Detail mentions host:port for operator visibility (T-04-03-03 accepted leak).
    assert "chromadb" in exc_info.value.detail
    assert "8000" in exc_info.value.detail


def test_open_collection_idempotent(
    fake_chromadb: type[_FakeChromadbModule],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two calls → both invoke get_or_create_collection with identical kwargs.

    chromadb 1.5+ semantics: get_or_create_collection returns existing
    collection without overwriting metadata if the name already exists.
    """
    from receptra.config import settings as receptra_settings
    monkeypatch.setattr(receptra_settings, "chroma_host", "http://chromadb:8000")

    sentinel = MagicMock(name="receptra_kb_collection")
    _install_http_client_with_collection(monkeypatch, fake_chromadb, sentinel)

    from receptra.rag.vector_store import open_collection

    a = open_collection()
    b = open_collection()
    assert a is sentinel
    assert b is sentinel

    # Latest HttpClient instance saw exactly one get_or_create call with the
    # cosine-pinned kwargs. The first invocation's kwargs were identical
    # (deterministic from settings + COLLECTION_NAME constant).
    inst = fake_chromadb.last_instance
    assert inst is not None
    expected = {"name": "receptra_kb", "metadata": {"hnsw:space": "cosine"}}
    assert inst.get_or_create_calls == [expected]
