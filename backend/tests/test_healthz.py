"""Smoke test for the /healthz endpoint (FND-04a)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_healthz_returns_200_ok(client: TestClient) -> None:
    """GET /healthz MUST return HTTP 200 with JSON body {'status': 'ok'}."""
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_healthz_content_type_is_json(client: TestClient) -> None:
    """GET /healthz MUST return application/json content-type."""
    response = client.get("/healthz")
    assert response.headers["content-type"].startswith("application/json")


def test_app_metadata_is_correct(client: TestClient) -> None:
    """OpenAPI schema reports the expected title + version for the service."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "Receptra"
    assert schema["info"]["version"] == "0.1.0"
