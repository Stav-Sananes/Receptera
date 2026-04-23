"""Shared pytest fixtures for Receptra backend tests."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app() -> FastAPI:
    """Return the FastAPI app instance for tests.

    Imported lazily so that test discovery does not require a populated .env.
    """
    from receptra.main import app as receptra_app

    return receptra_app


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """Return a FastAPI TestClient wrapping the app."""
    with TestClient(app) as test_client:
        yield test_client
