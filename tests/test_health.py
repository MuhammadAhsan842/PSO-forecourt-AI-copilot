"""Milestone 0 acceptance: /health returns 200."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.main import create_app


def test_health_ok() -> None:
    app = create_app()
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        payload = r.json()
        assert payload["status"] == "ok"
        assert payload["service"] == "pso-surveillance"
        assert "version" in payload


def test_version_endpoint() -> None:
    app = create_app()
    with TestClient(app) as client:
        r = client.get("/version")
        assert r.status_code == 200
        assert "version" in r.json()
