"""End-to-end: create an event via POST, get it back, mark feedback."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.main import create_app


def test_event_lifecycle(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PSO_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("PSO_SNAPSHOT_DIR", str(tmp_path / "snaps"))

    # Reset the settings cache so the new env is picked up
    from src.common import config as cfg

    cfg.get_settings.cache_clear()

    app = create_app()
    with TestClient(app) as client:
        r = client.post(
            "/api/v1/events",
            json={
                "kind": "restricted_entry",
                "camera_id": "ptz1",
                "track_id": 1,
                "confidence": 0.92,
                "payload": {"class": "person"},
            },
        )
        assert r.status_code == 201, r.text
        event = r.json()
        assert event["id"]

        r2 = client.get("/api/v1/events", params={"camera_id": "ptz1"})
        assert r2.status_code == 200
        events = r2.json()
        assert any(e["id"] == event["id"] for e in events)

        r3 = client.post(
            "/api/v1/feedback",
            json={"event_id": event["id"], "verdict": "true", "reviewer": "shift-a"},
        )
        assert r3.status_code == 201, r3.text

        r4 = client.get("/api/v1/stats/summary", params={"days": 1})
        assert r4.status_code == 200
        stats = r4.json()
        assert stats["feedback"]["true"] >= 1
