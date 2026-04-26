"""SQLite audit roundtrip + idempotent init + co-existence with stt_utterances.

Verifies the LLM-05 SQLite contract from Plan 03-05:
- Idempotent init_llm_audit_table (incl. parent-dir creation)
- INSERT/SELECT roundtrip preserves Hebrew transcript_hash byte-exact
- grounded boolean → INTEGER 0/1 mapping
- eval_count / prompt_eval_count nullable preservation
- Co-existence with Phase 2 stt_utterances on the same audit.sqlite file
- Fail-fast: insert before init raises sqlite3.OperationalError
- Default ts column populates with strftime UTC timestamp
- Indexes idx_llm_calls_ts + idx_llm_calls_status created
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from receptra.llm.audit import init_llm_audit_table, insert_llm_call
from receptra.llm.metrics import LlmCallMetrics


def _make(**over: Any) -> LlmCallMetrics:
    base: dict[str, Any] = {
        "request_id": "rid-1",
        "ts_utc": "2026-04-25T10:00:00+00:00",
        "transcript": "שלום",
        "transcript_hash": "abcd1234abcd1234",
        "text_len_chars": 4,
        "n_chunks": 1,
        "model": "dictalm3",
        "t_request_sent": 100.0,
        "t_first_token": 100.05,
        "t_done": 100.5,
        "eval_count": 12,
        "prompt_eval_count": 40,
        "status": "ok",
        "suggestions_count": 1,
        "grounded": True,
    }
    base.update(over)
    return LlmCallMetrics(**base)


def test_init_idempotent(tmp_path: Path) -> None:
    p = tmp_path / "data" / "audit.sqlite"
    init_llm_audit_table(p)
    init_llm_audit_table(p)  # second call is no-op
    assert p.exists()


def test_init_creates_parent_dir(tmp_path: Path) -> None:
    p = tmp_path / "fresh" / "deeply" / "nested" / "audit.sqlite"
    assert not p.parent.exists()
    init_llm_audit_table(p)
    assert p.parent.is_dir()


def test_init_creates_indexes(tmp_path: Path) -> None:
    p = tmp_path / "audit.sqlite"
    init_llm_audit_table(p)
    with sqlite3.connect(str(p)) as conn:
        idx_names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            )
        }
    assert "idx_llm_calls_ts" in idx_names
    assert "idx_llm_calls_status" in idx_names


def test_init_creates_llm_calls_table(tmp_path: Path) -> None:
    p = tmp_path / "audit.sqlite"
    init_llm_audit_table(p)
    with sqlite3.connect(str(p)) as conn:
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert "llm_calls" in names


def test_insert_writes_one_row(tmp_path: Path) -> None:
    p = tmp_path / "audit.sqlite"
    init_llm_audit_table(p)
    insert_llm_call(p, _make())
    with sqlite3.connect(str(p)) as conn:
        (n,) = conn.execute("SELECT COUNT(*) FROM llm_calls").fetchone()
    assert n == 1


def test_insert_three_rows(tmp_path: Path) -> None:
    p = tmp_path / "audit.sqlite"
    init_llm_audit_table(p)
    for i in range(3):
        insert_llm_call(p, _make(request_id=f"rid-{i}"))
    with sqlite3.connect(str(p)) as conn:
        (n,) = conn.execute("SELECT COUNT(*) FROM llm_calls").fetchone()
    assert n == 3


def test_insert_grounded_true_stores_one(tmp_path: Path) -> None:
    p = tmp_path / "audit.sqlite"
    init_llm_audit_table(p)
    insert_llm_call(p, _make(grounded=True))
    with sqlite3.connect(str(p)) as conn:
        (g,) = conn.execute("SELECT grounded FROM llm_calls").fetchone()
    assert g == 1


def test_insert_grounded_false_stores_zero(tmp_path: Path) -> None:
    p = tmp_path / "audit.sqlite"
    init_llm_audit_table(p)
    insert_llm_call(p, _make(grounded=False))
    with sqlite3.connect(str(p)) as conn:
        (g,) = conn.execute("SELECT grounded FROM llm_calls").fetchone()
    assert g == 0


def test_eval_count_nullable_preserves_null(tmp_path: Path) -> None:
    p = tmp_path / "audit.sqlite"
    init_llm_audit_table(p)
    insert_llm_call(
        p,
        _make(
            eval_count=None,
            prompt_eval_count=None,
            status="parse_error",
            t_first_token=None,
        ),
    )
    with sqlite3.connect(str(p)) as conn:
        ec, pec = conn.execute(
            "SELECT eval_count, prompt_eval_count FROM llm_calls"
        ).fetchone()
    assert ec is None
    assert pec is None


def test_transcript_hash_hebrew_byte_exact_through_sqlite(tmp_path: Path) -> None:
    p = tmp_path / "audit.sqlite"
    init_llm_audit_table(p)
    h = "abcd1234deadbeef"  # any 16-hex value — testing the TEXT roundtrip
    insert_llm_call(p, _make(transcript_hash=h))
    with sqlite3.connect(str(p)) as conn:
        (out,) = conn.execute("SELECT transcript_hash FROM llm_calls").fetchone()
    assert out == h


def test_insert_before_init_raises(tmp_path: Path) -> None:
    p = tmp_path / "audit.sqlite"
    # File doesn't exist; sqlite3.connect creates an empty file. Insert without
    # init_llm_audit_table should fail with OperationalError (no such table).
    with pytest.raises(sqlite3.OperationalError, match="no such table: llm_calls"):
        insert_llm_call(p, _make())


def test_coexistence_with_stt_utterances_table(tmp_path: Path) -> None:
    """Same `data/audit.sqlite` file holds both Phase 2 STT and Phase 3 LLM tables."""
    from receptra.stt.audit import init_audit_db
    from receptra.stt.metrics import UtteranceMetrics

    p = tmp_path / "audit.sqlite"
    init_audit_db(p)
    init_llm_audit_table(p)

    with sqlite3.connect(str(p)) as conn:
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert "stt_utterances" in names
    assert "llm_calls" in names

    # Both tables remain queryable after co-existence.
    insert_llm_call(p, _make())
    with sqlite3.connect(str(p)) as conn:
        (n_llm,) = conn.execute("SELECT COUNT(*) FROM llm_calls").fetchone()
        (n_stt,) = conn.execute("SELECT COUNT(*) FROM stt_utterances").fetchone()
    assert n_llm == 1
    assert n_stt == 0
    # UtteranceMetrics is in scope (proves Phase 2 import path is intact);
    # we don't insert here — test_chaos_disconnect.py owns the STT roundtrip.
    _ = UtteranceMetrics


def test_status_parse_error_writable(tmp_path: Path) -> None:
    p = tmp_path / "audit.sqlite"
    init_llm_audit_table(p)
    insert_llm_call(p, _make(status="parse_error"))
    with sqlite3.connect(str(p)) as conn:
        (s,) = conn.execute(
            "SELECT status FROM llm_calls WHERE status='parse_error'"
        ).fetchone()
    assert s == "parse_error"


def test_default_ts_populated_on_insert(tmp_path: Path) -> None:
    p = tmp_path / "audit.sqlite"
    init_llm_audit_table(p)
    insert_llm_call(p, _make())
    with sqlite3.connect(str(p)) as conn:
        (ts,) = conn.execute("SELECT ts FROM llm_calls").fetchone()
    assert ts and "T" in ts and ts.endswith("Z")


def test_request_id_byte_exact_through_sqlite(tmp_path: Path) -> None:
    p = tmp_path / "audit.sqlite"
    init_llm_audit_table(p)
    insert_llm_call(p, _make(request_id="rid-unique-abc-123"))
    with sqlite3.connect(str(p)) as conn:
        (rid,) = conn.execute("SELECT request_id FROM llm_calls").fetchone()
    assert rid == "rid-unique-abc-123"


def test_ttft_ms_and_total_ms_stored_as_int(tmp_path: Path) -> None:
    p = tmp_path / "audit.sqlite"
    init_llm_audit_table(p)
    # Power-of-2 fractions for exact float arithmetic.
    insert_llm_call(
        p,
        _make(t_request_sent=10.0, t_first_token=10.0625, t_done=10.5),
    )
    with sqlite3.connect(str(p)) as conn:
        ttft, total = conn.execute(
            "SELECT ttft_ms, total_ms FROM llm_calls"
        ).fetchone()
    assert ttft == 62
    assert total == 500


def test_ttft_ms_negative_one_when_no_token(tmp_path: Path) -> None:
    p = tmp_path / "audit.sqlite"
    init_llm_audit_table(p)
    insert_llm_call(
        p,
        _make(t_first_token=None, status="ollama_unreachable", eval_count=None),
    )
    with sqlite3.connect(str(p)) as conn:
        (ttft,) = conn.execute("SELECT ttft_ms FROM llm_calls").fetchone()
    assert ttft == -1
