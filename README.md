# PSO Forecourt AI Surveillance — Pilot

Edge AI for a PSO fuel station: **information staff trust and act on** — who was
served, what was sold, and did anything go wrong (drive-off, after-hours, unpaid).
All processing on-site; footage stays local. See [`CLAUDE.md`](./CLAUDE.md) for the
full brief and [`ROADMAP.md`](./ROADMAP.md) for per-milestone status.

> **The one rule (`CLAUDE.md` §0):** clear image first, then AI. The operational
> core (drive-off, after-hours, queue, loitering) ships on the wide view today.
> Meter/plate reading is built and verified on synthetic renders; it awaits the
> **camera-control gates (M1–M3)** on the real Dahua camera before any accuracy is
> claimed to the client.

## Quick start (offline demo — no camera needed)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'                 # core + test deps
pip install -e '.[inference]'           # optional: torch + ultralytics for real detection

# 1. base detector weights (COCO YOLO11n detects vehicles + people)
python -m scripts.bootstrap_models

# 2. generate synthetic day/night demo clips (already committed under tests/fixtures/)
python -m scripts.make_fixtures --label day   --out tests/fixtures/pump_A_day.mp4
python -m scripts.make_fixtures --label night --out tests/fixtures/pump_A_night.mp4

# 3. run detection + tracking + events over a clip
python -m scripts.replay_clip --input tests/fixtures/pump_A_day.mp4 --camera ptz1 --annotated out.mp4

# 4. serve the API + dashboard
docker compose up            # or: uvicorn src.api.main:app --port 8080
curl localhost:8080/health
```

Tests + lint:

```bash
pytest -q          # full suite, runs headless/offline
ruff check . && ruff format --check . && mypy src
```

## On-site bring-up (the gates)

1. Fill `.env` from `.env.example` — camera IP, ONVIF/RTSP ports, **admin** creds.
2. **M1 probe** — `python -m scripts.camera_probe --camera ptz1` prints the
   capability matrix (exposure / PTZ / focus / presets). If exposure **and**
   zoom/focus are both locked, STOP and renegotiate meter/plate scope (`CLAUDE.md` §13).
3. **M2 capture** — `python -m scripts.capture_baseline --label day|night`, then
   eyeball the meter/plate crops under `data/baseline/`. A human must be able to
   read them before any OCR is trusted.
4. **M3 presets** — lock the readable views in `config/presets.yaml`.

## What's real vs. pending

| Layer | Status |
|---|---|
| Operational core (zones, drive-off, after-hours, queue, loitering) | ✅ real, config-driven, tested |
| Detection + tracking (YOLO11 + ByteTrack) | ✅ real; needs `.[inference]` weights, degrades gracefully without |
| Seven-segment meter reader (`src/ocr/seven_seg.py`) | ✅ real classical-CV decoder; verified on synthetic renders |
| Pakistani-plate normalisation + format rules | ✅ real; deterministic, tested |
| Sale↔vehicle link + drive-off with amount | ✅ real, tested |
| Backend + WebSocket + React dashboard | ✅ real |
| Retention purge (DB + snapshots) | ✅ real, tested |
| Pilot report (precision from feedback, before/after) | ✅ real, tested |
| **Camera control gates M1–M3** | ⏳ code complete, **pending on-site camera** |
| **M9/M10 accuracy on real footage** | ⏳ pending a confirmed-readable capture |

Reading accuracy is claimed to the client only after M1–M3 pass on the real
camera and OCR runs on on-site frames (`CLAUDE.md` §0, §10).

## Privacy

Snapshots and footage stay on the local box; nothing is uploaded by default.
Retention is configurable (`PSO_RETENTION_DAYS`, default 30) and enforced by
`scripts/purge_retention.py` / `POST /api/v1/admin/purge`. See [`docs/PRIVACY.md`](./docs/PRIVACY.md).
