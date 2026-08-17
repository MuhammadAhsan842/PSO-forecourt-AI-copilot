"""Metrics — precision / false-alert-rate / latency.

Consumed by:
  * the FastAPI ``/stats/summary`` route (dashboard cards),
  * ``scripts/report.py`` (the before/after pilot report).

Deliberately in-memory + optionally-persisted; nothing here talks to Prometheus
or any external metric backend. Keeps the pilot deployable on a mini-PC.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from statistics import fmean, median


@dataclass
class LatencyTimer:
    label: str
    _start: float = field(default_factory=time.perf_counter)

    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self._start) * 1000.0


@dataclass
class MetricsAggregator:
    """Aggregates counts + latencies. Feed it via ``.record()`` from anywhere."""

    _counts: defaultdict[str, int] = field(default_factory=lambda: defaultdict(int))
    _true: defaultdict[str, int] = field(default_factory=lambda: defaultdict(int))
    _false: defaultdict[str, int] = field(default_factory=lambda: defaultdict(int))
    _latencies_ms: defaultdict[str, list[float]] = field(
        default_factory=lambda: defaultdict(list)
    )

    def record_event(self, kind: str) -> None:
        self._counts[kind] += 1

    def record_verdict(self, kind: str, verdict: str) -> None:
        if verdict == "true":
            self._true[kind] += 1
        elif verdict == "false":
            self._false[kind] += 1

    def record_latency(self, label: str, ms: float) -> None:
        buf = self._latencies_ms[label]
        buf.append(ms)
        if len(buf) > 5000:
            del buf[:2000]

    def precision(self, kind: str) -> float | None:
        t = self._true.get(kind, 0)
        f = self._false.get(kind, 0)
        total = t + f
        return (t / total) if total else None

    def false_alert_rate(self, kind: str) -> float | None:
        t = self._true.get(kind, 0)
        f = self._false.get(kind, 0)
        total = t + f
        return (f / total) if total else None

    def latency_stats(self, label: str) -> dict[str, float] | None:
        buf = self._latencies_ms.get(label) or []
        if not buf:
            return None
        return {
            "count": len(buf),
            "mean_ms": round(fmean(buf), 1),
            "p50_ms": round(median(buf), 1),
            "p95_ms": round(sorted(buf)[int(0.95 * (len(buf) - 1))], 1),
            "max_ms": round(max(buf), 1),
        }

    def snapshot(self) -> dict:
        out: dict = {"events": dict(self._counts), "by_kind": {}, "latency": {}}
        kinds = set(self._counts) | set(self._true) | set(self._false)
        for k in sorted(kinds):
            out["by_kind"][k] = {
                "true": self._true.get(k, 0),
                "false": self._false.get(k, 0),
                "precision": self.precision(k),
                "false_alert_rate": self.false_alert_rate(k),
            }
        for k in sorted(self._latencies_ms):
            out["latency"][k] = self.latency_stats(k)
        return out
