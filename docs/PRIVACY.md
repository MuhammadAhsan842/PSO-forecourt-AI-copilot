# Data Retention & Access Policy — PSO Forecourt AI Surveillance (Pilot)

Client: **PSO Pump 295-A, Airlines Society, Lahore** · Vendor: **M. Resolutions**

This policy is a **trust feature**, not boilerplate: PSO staff should be able to
read exactly what the system keeps, for how long, and who can see it.

## 1. What is stored

| Data | Purpose | Location |
|---|---|---|
| Event records (kind, time, camera, track id, confidence, payload) | Alerts + metrics | Local SQLite (`data/pso.db`) |
| Snapshots (one JPEG per alert) | Human verification of each alert | Local filesystem (`data/snapshots/YYYY-MM-DD/`) |
| Readings (meter amount/litres/rate, plate text) | Sale evidence + sale↔vehicle link | Local SQLite |
| Feedback (staff true/false verdict) | Accuracy measurement + tuning | Local SQLite |
| Camera health | Uptime / reconnect monitoring | Local SQLite |

We store **only what an alert needs**. No continuous footage is archived by the
pilot; snapshots are captured at alert time.

## 2. Where it lives

- **On the local on-site mini-PC only.** No external upload by default — no cloud,
  no third-party service (`CLAUDE.md` §4, §9).
- Camera credentials live in `.env` (never committed, never logged — the DB URL is
  sanitised in logs).

## 3. How long it is kept

- **Default retention: 30 days**, configurable via `PSO_RETENTION_DAYS`.
- **Auto-purge** removes DB rows (events, feedback, readings) and snapshot folders
  older than the window. Enforced by:
  - `python -m scripts.purge_retention` (schedule daily via cron/systemd on-site), or
  - `POST /api/v1/admin/purge` (on-demand; returns exactly what was removed).

## 4. Who can access it

- The dashboard runs on the local network for station staff and management.
- Snapshots are served only from the local box; access is bounded by the site LAN.
- No personal data leaves the premises under the pilot.

## 5. Deletion & audit

- Purge results are logged (`retention_purge`) with counts removed, so retention is
  auditable.
- On request, a specific event and its snapshot can be deleted ahead of the window.

*Owner: M. Resolutions · ahsanikram842@gmail.com · 0309 4644574*
