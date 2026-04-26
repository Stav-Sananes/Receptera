"""Settings + pyproject pin tests for Phase 4 Wave-0.

Behavior:
- 4 new RAG fields default per RESEARCH §Cluster 5 + §Hebrew Chunking + §BGE-M3 Pattern.
- RECEPTRA_RAG_* env prefix wires correctly through pydantic-settings.
- chromadb-client is pinned in backend/pyproject.toml [project].dependencies.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

import pytest

from receptra.config import Settings


def test_rag_settings_defaults() -> None:
    s = Settings()
    assert s.rag_min_similarity == 0.35
    assert s.rag_chunk_target_chars == 1500
    assert s.rag_chunk_overlap_chars == 200
    assert s.rag_embed_batch_size == 16


def test_rag_settings_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RECEPTRA_RAG_MIN_SIMILARITY", "0.5")
    # Force a fresh Settings instance (pydantic-settings re-reads env at __init__).
    s = Settings()
    assert s.rag_min_similarity == 0.5


def test_rag_settings_env_override_chunk_size(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RECEPTRA_RAG_CHUNK_TARGET_CHARS", "2000")
    monkeypatch.setenv("RECEPTRA_RAG_CHUNK_OVERLAP_CHARS", "300")
    monkeypatch.setenv("RECEPTRA_RAG_EMBED_BATCH_SIZE", "32")
    s = Settings()
    assert s.rag_chunk_target_chars == 2000
    assert s.rag_chunk_overlap_chars == 300
    assert s.rag_embed_batch_size == 32


def test_chromadb_client_pinned() -> None:
    """pyproject.toml [project].dependencies must contain chromadb-client>=1.5.8."""
    # Walk up from this file to backend/pyproject.toml.
    here = Path(__file__).resolve()
    backend_dir: Path | None = None
    for parent in here.parents:
        candidate = parent / "pyproject.toml"
        if candidate.exists() and parent.name == "backend":
            backend_dir = parent
            break
    assert backend_dir is not None, "backend/pyproject.toml not found in ancestors"
    pyproject = backend_dir / "pyproject.toml"
    with pyproject.open("rb") as fh:
        data = tomllib.load(fh)
    deps: list[str] = data["project"]["dependencies"]
    matches = [d for d in deps if d.startswith("chromadb-client")]
    assert matches, f"chromadb-client not in dependencies: {deps}"
    spec = matches[0]
    assert ">=1.5.8" in spec, f"chromadb-client spec missing >=1.5.8: {spec!r}"
    # Belt-and-suspenders: do NOT pin the full chromadb package (would pull
    # onnxruntime/pulsar-client/tokenizers per RESEARCH §Cluster 1 anti-pattern).
    bare_chromadb = [
        d for d in deps if d.startswith("chromadb") and not d.startswith("chromadb-client")
    ]
    assert not bare_chromadb, f"full chromadb package must NOT be pinned: {bare_chromadb}"


def test_python_version_marker() -> None:
    """Smoke: ensure Python 3.12 is in use (matches pyproject requires-python)."""
    assert sys.version_info >= (3, 12)
