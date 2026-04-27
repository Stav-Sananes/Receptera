"""Aggregate audit reads — exposes summary stats over stt_utterances +
pipeline_runs without leaking raw transcripts.

PII boundary: text columns NEVER cross this boundary. Only counts +
latency aggregates are returned. Hebrew transcripts stay in SQLite.
"""
