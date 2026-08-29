"""Meter API: health + synthetic fill persist readings/events."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.main import create_app


def test_meter_health_and_simulate(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PSO_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("PSO_SNAPSHOT_DIR", str(tmp_path / "snaps"))
    from src.common import config as cfg

    cfg.get_settings.cache_clear()

    app = create_app()
    with TestClient(app) as client:
        r = client.get("/api/v1/meter/health")
        assert r.status_code == 200, r.text
        assert "pumps" in r.json()

        r2 = client.get("/api/v1/meter/pumps")
        assert r2.status_code == 200
        assert any(p["id"] == "m1" for p in r2.json())

        r3 = client.post("/api/v1/meter/simulate-fill")
        assert r3.status_code == 200, r3.text
        sim = r3.json()
        assert sim["billed"] is False
        kinds = {e["kind"] for e in sim["events"]}
        assert "meter_fill_start" in kinds
        assert "meter_fill_final" in kinds
        last = sim["ticks"][-1]
        assert last["provenance"] == "camera-observed"
        assert last["camera_observed"] is True

        r4 = client.get("/api/v1/meter/readings")
        assert r4.status_code == 200
        assert len(r4.json()) >= 1

        events = client.get("/api/v1/events", params={"kind": "meter_fill_final"}).json()
        assert events
        assert events[0]["payload"]["schema_version"] == 2
        assert events[0]["payload"]["billed"] is False
        assert events[0]["payload"]["amount"] is not None

        review = client.get("/api/v1/meter/review").json()
        assert isinstance(review, list)
        metrics = client.get("/api/v1/meter/metrics").json()
        assert "metrics" in metrics
