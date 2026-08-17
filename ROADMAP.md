# Milestone Roadmap

Execute in order. Each milestone ends with a passing test AND a runnable demo. No skipping.

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
