# Milestone Roadmap

Execute in order. Each milestone ends with a passing test AND a runnable demo. No skipping.

## Status at a glance

| M | Milestone | Status |
|---|---|---|
| M0 | Scaffold & rails | ✅ done |
| M1 | Camera-control probe *(gate)* | ⏳ code complete — **pending on-site camera** |
| M2 | Blur-free human-verified capture *(gate)* | ⏳ code complete — **pending on-site camera** |
| M3 | Repeatable sharp presets | ⏳ code complete — **pending on-site camera** |
| M4 | RTSP ingest & baseline | ✅ code complete (unrun against a 30-min live stream) |
| M5 | Detection & tracking | ✅ real; needs `.[inference]` weights (`bootstrap_models.py`) |
| M6 | Operational core | ✅ done, tested |
| M7 | Backend, storage & dashboard | ✅ done |
| M8 | Choreographed capture sequencer | ✅ logic done (unrun on camera) |
| M9 | Meter reading | ✅ real seven-seg reader + arithmetic check; verified on synthetic renders, **awaits on-site frames** |
| M10 | Plate reading & sale↔vehicle link | ✅ PK normalisation + drive-off with amount; **awaits on-site frames** |
| M11 | Prove, tune & pilot report | ✅ report joins feedback + before/after; runs once data accrues |

Gates M1–M3 can only be *passed* on the real Dahua camera (§0, §12). M9/M10
accuracy is claimed to the client only after a confirmed-readable capture exists.

## M0 — Scaffold & rails
Runnable skeleton with config, logging, tests, Docker, metrics stub.

- Demo: `docker compose up` → `curl http://localhost:8080/health` returns 200.
- Test: `pytest -q` green (health, config, tracker, event engine, meter/plate skeleton, link, API lifecycle).

## M1 — Camera-control probe *(gate)*
Find out, on ONE camera, exactly what the API lets us change.

- Command: `python -m scripts.camera_probe --camera ptz1`
- Acceptance: exposure OR (ptz + focus) confirmed on a real camera.
- **If both are locked, STOP and escalate — meter/plate scope must be renegotiated.**

## M2 — Blur-free, human-verified capture *(gate)*
Meter and plate readable to a HUMAN, day AND night.

- Use `python -m scripts.capture_baseline --label day` / `--label night`.
- Review the stills under `data/baseline/`.
- **If a human cannot read it, no AI will. Fix the capture first.**

## M3 — Repeatable sharp presets
Lock the readable views. Presets in `config/presets.yaml`, recall verified sharp.

## M4 — RTSP ingest & baseline (reliability)
`IngestWorker` runs ≥ 30 min without crashing; drops recover.

## M5 — Detection & tracking
YOLO + ByteTrack. `python -m scripts.replay_clip --input tests/fixtures/pump_A_afternoon.mp4 --camera ptz1 --annotated out.mp4`.

## M6 — Operational core
Rules from `zones.yaml` fire on real footage:
`after_hours_presence`, `queue_dwell`, `restricted_entry`, `loitering`, `vehicle_settled_at_pump`.

## M7 — Backend, storage & live dashboard
Events persist; live WebSocket feed; one-tap True/False in the React dashboard.

## M8 — Choreographed capture sequencer
On `vehicle_settled_at_pump`: METER preset → sharp still → PLATE preset on exit → sharp still.

## M9 — Meter reading
Sale-happened + amount, validated by `amount ≈ litres × rate`.

## M10 — Plate reading & sale↔vehicle link
Sale attributed to the vehicle. Drive-off fires with an unpaid amount.

## M11 — Prove, tune & pilot report
Metrics loop + weekly tuning + `python -m scripts.report --days 7`.
