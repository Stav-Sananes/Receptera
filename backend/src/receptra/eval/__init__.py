"""Receptra evaluation harness — automated quality regression tests.

Runs over labelled Hebrew test datasets and produces accuracy / latency
reports. Intended for periodic regression runs against a live Ollama,
not part of the unit-test suite.

Modules:
    intent_eval — classifies a labelled set of Hebrew utterances and
                  reports per-class precision/recall + overall accuracy.
    summary_eval — runs the post-call summary on a labelled set of
                   transcripts and scores topic / action_item recall.
    datasets/ — JSON fixtures with expected outputs.
"""
