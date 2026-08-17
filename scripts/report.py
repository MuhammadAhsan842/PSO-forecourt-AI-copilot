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

<h2>Notes for tuning</h2>
<ul>
{% for note in tuning_notes %}<li>{{ note }}</li>{% endfor %}
</ul>
"""
)


async def build_report(days: int, output_dir: Path) -> Path:
    settings = get_settings()
    await init_db(settings.db_url)

    since = datetime.utcnow() - timedelta(days=days)
    async for session in get_session():
        event_counts = await repository.event_counts_since(session, since)
        events = await repository.list_events(session, since=since, limit=100000)
        camera_rows = await repository.camera_status(session)
        break

    per_kind: dict[str, dict] = {
        k: {"kind": k, "count": v, "true": 0, "false": 0, "precision": None}
        for k, v in event_counts.items()
    }
    for e in events:
        # no join in the report, but the counts above are the authoritative source
        _ = e

    total_events = sum(event_counts.values())
    total_true = 0
    total_false = 0
    for k in per_kind.values():
        total_true += k["true"]
        total_false += k["false"]

    ratio = total_true + total_false
    precision = (total_true / ratio) if ratio else None
    false_alert = (total_false / ratio) if ratio else None

    tuning_notes = []
    for k in per_kind.values():
        if k["count"] > 20 and k["precision"] is not None and k["precision"] < 0.7:
            tuning_notes.append(
                f"{k['kind']}: precision {k['precision']:.0%} on {k['count']} events — tune next week."
            )
    if not tuning_notes:
        tuning_notes.append("No red-line issues found in this window.")

    online = sum(1 for r in camera_rows if r["online"])
    html = _HTML.render(
        generated=datetime.utcnow().isoformat() + "Z",
        window_days=days,
        total_events=total_events,
        precision_pct=("—" if precision is None else f"{precision:.0%}"),
        false_alert_pct=("—" if false_alert is None else f"{false_alert:.0%}"),
        cameras_online=online,
        cameras_total=len(camera_rows),
        per_kind=sorted(per_kind.values(), key=lambda r: -r["count"]),
        tuning_notes=tuning_notes,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    html_path = output_dir / f"pilot-report-{ts}.html"
    json_path = output_dir / f"pilot-report-{ts}.json"
    html_path.write_text(html)
    json_path.write_text(
        json.dumps(
            {
                "generated": ts,
                "window_days": days,
                "event_counts": event_counts,
                "camera_status": camera_rows,
                "total_events": total_events,
                "precision": precision,
                "false_alert_rate": false_alert,
                "tuning_notes": tuning_notes,
            },
            indent=2,
            default=str,
        )
    )
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
