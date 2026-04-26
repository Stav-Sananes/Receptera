"""RAG-test scaffolding for Phase 4.

The ``live`` marker is registered in tests/llm/conftest.py (Plan 03-01).
This module publishes ``rag_live_test_enabled()`` gated on the SEPARATE
env var ``RECEPTRA_RAG_LIVE_TEST`` so RAG and LLM live tests can be
toggled independently — RAG live tests need ChromaDB up + bge-m3 pulled,
LLM live tests need DictaLM pulled.
"""

from __future__ import annotations

import os


def rag_live_test_enabled() -> bool:
    """True iff the developer opted into live RAG (Chroma + Ollama-bge-m3) tests."""
    return bool(os.getenv("RECEPTRA_RAG_LIVE_TEST"))
