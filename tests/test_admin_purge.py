"""Admin purge endpoint returns a structured summary of what was removed."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.main import create_app


def test_purge_endpoint_returns_summary() -> None:
    app = create_app()
    with TestClient(app) as client:
        r = client.post("/api/v1/admin/purge", params={"retention_days": 30})
        assert r.status_code == 200
        body = r.json()
        assert body["retention_days"] == 30
        assert "db_rows_removed" in body
        assert "snapshot_folders_removed" in body
