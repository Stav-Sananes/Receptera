"""Shared scaffolding for tests/llm/.

Phase 3 Wave 0: this conftest publishes the ``live_test_enabled`` helper used
by every live LLM test. The ``live`` pytest marker itself is registered in the
top-level ``tests/conftest.py`` (Plan 04-01) so it is visible to both
``tests/llm`` and ``tests/rag`` under ``--strict-markers`` regardless of which
test path is collected.
"""

from __future__ import annotations

import os


def live_test_enabled() -> bool:
    """True iff the developer opted into live-Ollama tests for this run."""
    return bool(os.getenv("RECEPTRA_LLM_LIVE_TEST"))
