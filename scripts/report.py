"""Milestone 11 — before/after pilot report generator.

Pulls counts + precision from the DB (via the FastAPI /stats route or directly)
and renders a simple HTML + JSON report under ``data/reports/``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path

import httpx
from jinja2 import Template

from src.common.config import get_settings
from src.common.logging import setup_logging
from src.storage import repository
from src.storage.db import get_session, init_db

_HTML = Template(
    """
<!doctype html>
<meta charset="utf-8">
<title>PSO Pilot Report — {{ generated }}</title>
<style>
  body { font: 14px/1.4 -apple-system, system-ui, sans-serif; padding: 32px; color: #111; }
  h1 { margin-top: 0; }
  h2 { margin-top: 2em; }
  table { border-collapse: collapse; margin-top: .5em; }
  th, td { border: 1px solid #ddd; padding: 6px 10px; text-align: left; }
  th { background: #f6f7f9; }
  .kpi { display: inline-block; padding: 12px 16px; border: 1px solid #e5e7eb;
         border-radius: 8px; margin-right: 12px; margin-bottom: 12px; }
  .kpi small { color: #6b7280; display: block; }
  .kpi strong { font-size: 22px; }
</style>
<h1>PSO Forecourt AI Surveillance — Pilot Report</h1>
<p><small>Generated {{ generated }} · window: last {{ window_days }} days</small></p>

<h2>Headline</h2>
<div class="kpi"><small>Events</small><strong>{{ total_events }}</strong></div>
<div class="kpi"><small>Precision (staff-confirmed)</small><strong>{{ precision_pct }}</strong></div>
<div class="kpi"><small>False-alert rate</small><strong>{{ false_alert_pct }}</strong></div>
<div class="kpi"><small>Cameras online</small><strong>{{ cameras_online }} / {{ cameras_total }}</strong></div>

<h2>By event kind</h2>
<table>
  <tr><th>kind</th><th>count</th><th>true</th><th>false</th><th>precision</th></tr>
  {% for row in per_kind %}
  <tr><td>{{ row.kind }}</td><td>{{ row.count }}</td><td>{{ row.true }}</td>
      <td>{{ row.false }}</td><td>{{ row.precision or "—" }}</td></tr>
  {% endfor %}
</table>

<h2>Before / after (this window vs the previous one)</h2>
<table>
  <tr><th>metric</th><th>previous</th><th>current</th><th>Δ</th></tr>
  {% for row in before_after %}
  <tr><td>{{ row.metric }}</td><td>{{ row.previous }}</td><td>{{ row.current }}</td>
      <td>{{ row.delta }}</td></tr>
  {% endfor %}
</table>

<h2>Notes for tuning</h2>
<ul>
{% for note in tuning_notes %}<li>{{ note }}</li>{% endfor %}
</ul>
"""
)


def compose_report(
    *,
    days: int,
    event_counts: dict[str, int],
    feedback_by_kind: dict[str, dict[str, int]],
    camera_rows: list[dict],
    prev_event_counts: dict[str, int] | None = None,
    prev_feedback_by_kind: dict[str, dict[str, int]] | None = None,
) -> dict:
    """Pure report assembly — no I/O, so it is unit-tested directly.

    Precision comes from feedback JOINED to its event's kind (the fix: the old
    report never joined, so precision was always zero).
    """

    def _per_kind(counts: dict[str, int], fb: dict[str, dict[str, int]]) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for kind, count in counts.items():
            t = fb.get(kind, {}).get("true", 0)
            f = fb.get(kind, {}).get("false", 0)
            precision = (t / (t + f)) if (t + f) else None
            out[kind] = {
                "kind": kind,
                "count": count,
                "true": t,
                "false": f,
                "precision": (None if precision is None else round(precision, 3)),
            }
        return out

    per_kind = _per_kind(event_counts, feedback_by_kind)

    total_events = sum(event_counts.values())
    total_true = sum(k["true"] for k in per_kind.values())
    total_false = sum(k["false"] for k in per_kind.values())
    reviewed = total_true + total_false
    precision = (total_true / reviewed) if reviewed else None
    false_alert = (total_false / reviewed) if reviewed else None

    tuning_notes: list[str] = []
    for k in sorted(per_kind.values(), key=lambda r: (r["precision"] or 1.0)):
        if k["true"] + k["false"] >= 5 and k["precision"] is not None and k["precision"] < 0.7:
            tuning_notes.append(
                f"{k['kind']}: precision {k['precision']:.0%} on "
                f"{k['true'] + k['false']} reviewed — worst offender, tune next."
            )
    if not tuning_notes:
        tuning_notes.append("No rule below the 70% precision line in this window.")

    # Before/after vs the preceding window of equal length.
    before_after: list[dict] = []
    if prev_event_counts is not None:
        prev_total = sum(prev_event_counts.values())
        prev_pk = _per_kind(prev_event_counts, prev_feedback_by_kind or {})
        prev_true = sum(k["true"] for k in prev_pk.values())
        prev_false = sum(k["false"] for k in prev_pk.values())
        prev_reviewed = prev_true + prev_false
        prev_precision = (prev_true / prev_reviewed) if prev_reviewed else None

        def _pct(x: float | None) -> str:
            return "—" if x is None else f"{x:.0%}"

        def _delta(cur: float | None, prev: float | None) -> str:
            if cur is None or prev is None:
                return "—"
            return f"{(cur - prev) * 100:+.0f} pts"

        before_after = [
            {"metric": "events", "previous": prev_total, "current": total_events,
             "delta": total_events - prev_total},
            {"metric": "precision", "previous": _pct(prev_precision),
             "current": _pct(precision), "delta": _delta(precision, prev_precision)},
        ]

    online = sum(1 for r in camera_rows if r["online"])
    return {
        "generated": datetime.utcnow().isoformat() + "Z",
        "window_days": days,
        "total_events": total_events,
        "precision": precision,
        "false_alert_rate": false_alert,
        "precision_pct": ("—" if precision is None else f"{precision:.0%}"),
        "false_alert_pct": ("—" if false_alert is None else f"{false_alert:.0%}"),
        "cameras_online": online,
        "cameras_total": len(camera_rows),
        "per_kind": sorted(per_kind.values(), key=lambda r: -r["count"]),
        "before_after": before_after,
        "tuning_notes": tuning_notes,
    }


async def build_report(days: int, output_dir: Path) -> Path:
    settings = get_settings()
    await init_db(settings.db_url)

    now = datetime.utcnow()
    since = now - timedelta(days=days)
    prev_since = now - timedelta(days=2 * days)
    async for session in get_session():
        event_counts = await repository.event_counts_since(session, since)
        feedback_by_kind = await repository.feedback_by_kind_since(session, since)
        prev_all = await repository.event_counts_since(session, prev_since)
        prev_fb = await repository.feedback_by_kind_since(session, prev_since)
        camera_rows = await repository.camera_status(session)
        break

    # Previous window = [prev_since, since); subtract current from the 2x window.
    prev_event_counts = {
        k: max(0, prev_all.get(k, 0) - event_counts.get(k, 0))
        for k in set(prev_all) | set(event_counts)
    }

    ctx = compose_report(
        days=days,
        event_counts=event_counts,
        feedback_by_kind=feedback_by_kind,
        camera_rows=camera_rows,
        prev_event_counts=prev_event_counts,
        prev_feedback_by_kind=prev_fb,
    )

    html = _HTML.render(**ctx)
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = now.strftime("%Y%m%dT%H%M%SZ")
    html_path = output_dir / f"pilot-report-{ts}.html"
    json_path = output_dir / f"pilot-report-{ts}.json"
    html_path.write_text(html)
    json_path.write_text(json.dumps(ctx, indent=2, default=str))
    return html_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--out", type=Path, default=Path("./data/reports"))
    parser.add_argument("--api", help="pull from live API instead of DB")
    args = parser.parse_args(argv)

    setup_logging(level="INFO", json_output=False)

    if args.api:
        r = httpx.get(f"{args.api.rstrip('/')}/api/v1/stats/summary", params={"days": args.days})
        print(r.text)
        return 0

    path = asyncio.run(build_report(args.days, args.out))
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":       # pragma: no cover
    raise SystemExit(main())
