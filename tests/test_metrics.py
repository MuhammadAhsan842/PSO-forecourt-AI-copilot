"""Metrics aggregator: precision, false-alert rate, latency, snapshot."""

from __future__ import annotations

from src.metrics.logger import MetricsAggregator


def test_precision_and_false_alert_rate() -> None:
    m = MetricsAggregator()
    for _ in range(3):
        m.record_verdict("drive_off", "true")
    m.record_verdict("drive_off", "false")
    assert m.precision("drive_off") == 0.75
    assert m.false_alert_rate("drive_off") == 0.25
    # Unseen kind → None, never a misleading zero.
    assert m.precision("loitering") is None


def test_latency_stats() -> None:
    m = MetricsAggregator()
    for v in [100.0, 200.0, 300.0, 400.0]:
        m.record_latency("capture_to_alert", v)
    stats = m.latency_stats("capture_to_alert")
    assert stats is not None
    assert stats["count"] == 4
    assert stats["mean_ms"] == 250.0
    assert stats["max_ms"] == 400.0


def test_snapshot_shape() -> None:
    m = MetricsAggregator()
    m.record_event("drive_off")
    m.record_verdict("drive_off", "true")
    snap = m.snapshot()
    assert snap["events"]["drive_off"] == 1
    assert snap["by_kind"]["drive_off"]["precision"] == 1.0
