"""Shared scaffolding for tests/llm/.

Phase 3 Wave 0: this conftest must NOT import ``receptra.llm.*`` because that
package does not exist yet (created by Plan 03-02). It exists only to:

1. Register the ``live`` pytest marker so ``--strict-markers`` accepts it.
2. Publish the ``live_test_enabled`` helper used by every live test.

Plans 03-02..03-06 add fixtures here (e.g. ``mock_ollama_client``) once the
``receptra.llm`` package is real.
"""

from __future__ import annotations

import os

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "live: opt-in test against live host Ollama (set RECEPTRA_LLM_LIVE_TEST=1)",
    )


def live_test_enabled() -> bool:
    """True iff the developer opted into live-Ollama tests for this run."""
    return bool(os.getenv("RECEPTRA_LLM_LIVE_TEST"))
