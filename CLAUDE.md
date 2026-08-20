# CLAUDE.md — PSO Forecourt AI Surveillance (Pilot) · Final Plan

> **Project brief & execution plan for Claude Code.**
> Read this file fully before writing any code. Follow the milestones **in strict order** —
> each is a **gate** that must pass before the next begins. Produce a runnable demo + passing
> tests at the end of every milestone. Do not build ahead.

Client: **PSO Pump — 295-A, Airlines Society, Lahore** · Vendor: **M. Resolutions**
Engagement: **1.5-month pilot** on the client's **existing Dahua PTZ (8MP/4K) cameras**. No new hardware.

---

## 0. The one rule that orders this whole plan

**Get a clear, readable image first — then build AI on top of it.**
AI on a clear image is easy. AI on a blurry image is impossible. So the sequence is strictly:

> **clear image → repeatable clear image → understand the scene → capture the right moments →
> read them → connect them → prove it.**

You never build on an unproven layer. If an early gate fails on a camera, you learn it in an
afternoon — not after building a pipeline that had nothing readable to work with.

---

## 1. What "success" means (read first)

The product is **not** "an AI that watches cameras." It is **information PSO trusts and acts on**:
who served whom, what was sold, and did anything go wrong (drive-off, after-hours, unpaid).
Success is measured at the pump:

- Staff open the dashboard daily and act on alerts.
- Real incidents are caught; false alerts stay low enough that staff keep trusting it.
- Sales get linked to vehicles; drive-offs are flagged with an amount.
- At pilot's end we show a **measured before/after review** that justifies the subscription.

Every technical choice serves **trust and adoption**, not model novelty.

---

## 2. Guiding principles

1. **Clear image before AI.** Camera-API control and human-verified readability gate everything.
2. **Reliable core first.** Operational events ship value in week one on the wide view; the harder
   meter/plate reading comes only after the image is proven readable.
3. **Measure from day one.** Precision, false-alert rate, latency logged for every event type.
4. **Edge-first, privacy-first.** All processing on-site; footage stays local; retention documented.
5. **Human-in-the-loop.** Every alert carries a snapshot + one-tap true/false. That feedback tunes
   the system and proves accuracy to the client.
6. **Iterate on real misses.** Weekly: fix the single worst false-alert/miss, re-measure.
7. **Fail loud, degrade gracefully.** A dead camera alerts and reconnects; it never crashes the pipeline.

---

## 3. The capture reality (why the ordering is what it is)

- The **current wide camera cannot read the meter or plate** — those targets are ~30 px tall and
  glare out. No software invents digits that weren't captured.
- The fix is **camera-side, over the API**: drive **exposure/shutter/WDR** to tame the glary display,
  and (if PTZ) **zoom + lock focus** onto the target so it becomes genuinely readable.
- Post-capture "enhancement" (sharpen/denoise) helps *viewing* a little but **cannot manufacture
  readable digits** — never rely on it for meter or plate.
- Therefore the whole meter/plate capability **depends on what the Dahua API exposes**. That is the
  first thing to verify, on one camera, before promising anything.

---

## 4. Architecture

```
[Dahua PTZ cameras] --RTSP--> [Ingest workers] --frames--> [Inference: YOLO + tracker]
        ^  (control: ONVIF/Dahua API)                              |
        |  exposure / zoom / focus / presets              detections + tracks
   [Camera controller] <---- trigger (vehicle at pump) ----[Event engine (zones/lines/sequence)]
        |                                                          |
   [Choreographed capture: presets -> sharp stills]       events / alerts (+ snapshot)
        |                                                          v
   meter / plate crops --> [OCR: 7-seg digits, plate]     [FastAPI backend] <--> [SQLite + snapshot store]
                                   |                             |  ^                    |
                            reading + validation           WebSocket/SSE          metrics logger
                                   |                             v  |                    |
                                   +--------> sale <-> vehicle link -> [React dashboard] <- true/false
```

---

## 5. Tech stack (with rationale)

| Layer | Choice | Why |
|---|---|---|
| Language | **Python 3.11+** | Vision ecosystem; fast iteration. |
| Detection | **Ultralytics YOLO (v11)** | SOTA, simple, exports to ONNX/TensorRT. |
| Tracking | **ByteTrack / BoT-SORT** (in Ultralytics) | One stable id per vehicle/person. |
| Geometry / zones | **Shapely** | Point-in-polygon, line-crossing. |
| Camera control | **ONVIF (onvif-zeep)** + **Dahua HTTP API** | Exposure, PTZ move/zoom/focus, presets. |
| Video I/O | **OpenCV** + **FFmpeg** (**GStreamer** if RTSP is flaky) | Streaming + reconnect. |
| Meter/plate OCR | **YOLO region detect** + **digit model fine-tuned on this dispenser's font**; plate model fine-tuned on **Pakistani plates** | Generic OCR fails on 7-seg + local plates. |
| Inference accel | **PyTorch** (dev) -> **ONNX Runtime / TensorRT** (deploy) | Portable dev, fast edge. |
| Backend / API | **FastAPI** + **Uvicorn** | Async; WebSocket/SSE live feed. |
| Database | **SQLite** (WAL) for pilot | Zero-ops; Postgres later if needed. |
| Snapshot store | Local filesystem, path in DB | Simple, private, on-site. |
| Dashboard | **React + Vite + TypeScript + Tailwind** | Build the real UI from our mockup. |
| Config | **pydantic-settings** + **YAML** (cameras, zones, presets, thresholds) | Retune without code changes. |
| Packaging | **Docker + docker-compose** | Reproducible edge deploy; portable. |
| Tests | **pytest** + sample clips as fixtures | Every milestone verifiable. |
| Logging | **loguru** (structured) | Readable, shippable logs. |

Keep it a single docker-compose stack one person can run and debug. No heavy infra (Kafka, k8s) in the pilot.

---

## 6. Compute & deployment

- **Local mini-PC with a modern NVIDIA GPU** (RTX 4060/4070-class) on-site.
- **Not cloud** (4K RTSP upload is bandwidth-heavy, laggy, privacy-poor). **Not Jetson yet**
  (harder dev, pricier per performance) — revisit for embedded rollout after the pilot.
- Keep it **Dockerized** so it can move to Jetson/cloud later.
- Run analytics at **5-10 FPS**; cap concurrent decoded streams to what the GPU handles.

---

## 7. Repository structure

```
pso-surveillance/
├─ CLAUDE.md
├─ docker-compose.yml
├─ .env.example                # RTSP + camera creds via env, never committed
├─ config/
│  ├─ cameras.yaml             # id, name, rtsp_url_env, fps, role, is_ptz
│  ├─ presets.yaml             # per camera: named presets w/ pan/tilt/zoom/focus/exposure
│  ├─ zones.yaml               # polygons, lines, dwell thresholds, after-hours window
│  └─ settings.yaml            # model paths, confidence, retention, enabled rules, timezone
├─ models/                     # YOLO + digit/plate weights (versioned)
├─ src/
│  ├─ cameractl/               # ONVIF/Dahua control: exposure, ptz, focus, presets, probe
│  ├─ ingest/                  # RTSP workers, reconnect, frame sampling, health
│  ├─ inference/               # detection + tracking
│  ├─ events/                  # zone/line/dwell + transaction-sequence logic
│  ├─ capture/                 # choreographed capture sequencer (preset -> sharp still)
│  ├─ ocr/                     # 7-seg meter reader + plate reader + validation
│  ├─ link/                    # sale <-> vehicle association
│  ├─ api/                     # FastAPI app, websocket, routes
│  ├─ storage/                 # DB models, snapshot store
│  ├─ metrics/                 # precision/recall/false-alert/latency logging
│  └─ common/                  # config, logging, types
├─ dashboard/                  # React + Vite app (from the mockup)
├─ tests/  (fixtures: day + night clips)
└─ scripts/                    # camera_probe.py, capture_baseline.py, replay_clip.py, report.py
```

---

## 8. Coding standards

- Type hints everywhere; **ruff** + **mypy**; format with **ruff format**.
- Small, single-responsibility modules; no 500-line files.
- **All tunables in `config/`** (confidence, FPS, dwell seconds, zones, presets, retention) — never hard-coded.
- Every module ships tests. "Done" = tests pass **and** the demo runs.
- Structured logging (camera id + track id + event on every alert); never `print`.
- Graceful failure: dead camera logs + retries, never crashes the pipeline.
- Secrets only via `.env`/environment.

---

## 9. Data & privacy

- Footage/snapshots stay **on the local box**; no external upload by default.
- **Retention configurable** (default ~30 days) with auto-purge.
- Store only what's needed: event, snapshot, timestamp, camera, track id, confidence, reading.
- Ship a documented **retention & access policy** for the client — a trust feature (see `docs/PRIVACY.md`).

---

## 10. Metrics & definition of done

Per event/reading type, logged and shown on the dashboard:
**true/false counts -> precision · missed -> recall estimate · false-alert rate · latency (capture->alert).**

**Pilot core done** = documented precision/false-alert for priority events (drive-off, after-hours,
queue) on real footage + a dashboard staff have used + a generated before/after report.
**Meter/plate done** = read-accuracy on real footage from a *confirmed-readable* capture, with the
litres×rate validation active.

---

## 11. Milestone plan — execute in strict order

See `ROADMAP.md` for the current per-milestone status. Milestones M1–M3 are **hardware gates** that
can only be *passed* against the real on-site Dahua camera; the software for them is complete and
verified against mocks/synthetic renders, and is flagged **pending on-site calibration** until run
live. M9/M10 reading accuracy is likewise *validated on synthetic renders* and awaits real footage
from a confirmed-readable capture (per §0 and §12) before accuracy is claimed to the client.

---

## 11b. Two-model strategy (Opus 4.8 + Sonnet 5)

Opus 4.8 for judgment & design (gate milestones M1–M3, the hard AI in M8–M10, subtle debugging,
reviewing Sonnet's work). Sonnet 5 for well-specified execution (scaffolding, config wiring, ingest,
CRUD/API routes, dashboard components, tests to a defined interface). One model active on the repo
at a time; **git is the handoff** — commit per milestone with the milestone number in the message.
Never send a MONEY/evidence judgment (M9 meter validation, M10 plate↔sale link) to the cheaper model.

---

## 12. How Claude Code should work

- **One milestone at a time.** Finish -> test -> demo -> commit -> next.
- **Every task ends with a test and a runnable demo.** No "trust me."
- **Keep it runnable offline** on saved clips (`replay_clip.py`) so progress never depends on live cameras.
- **When blocked by missing input** (RTSP URL, camera creds, GPU, a real clip), **stop and ask** — never fabricate
  credentials or silently mock away the hard part (camera control, readability).
- **Respect the gates:** do not claim meter/plate accuracy (M9-M10) until M1-M3 prove a human-readable capture exists.
- **Update this file** when an architectural decision changes.

---

## 13. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Camera API locks exposure/zoom/focus | Milestone 1 probe first; if locked, renegotiate meter/plate scope before building. |
| Meter/plate unreadable even zoomed | Milestone 2 human check; flag lighting/angle as client-side dependency; don't promise on the wide view. |
| One PTZ can't catch all stages in time | Priority order (meter -> plate -> people); trigger-driven, not patrol; note 2nd-camera path. |
| Totalizer is mechanical/separate | Scoped as a feasibility item, tested on one pump, not promised. |
| 7-seg/plate OCR misreads money | Many-frame voting + litres×rate self-check; always keep the original snapshot. |
| RTSP instability | Reconnect + camera-health alerts (Milestone 4). |
| GPU can't handle all streams at 30 FPS | 5-10 FPS, cap streams, ONNX/TensorRT. |
| "Looks done" but nothing integrates | Milestone gates with end-to-end demos. |

---

## 14. Pilot handover deliverables (weeks 5-6)

1. Running system on the on-site box (docker-compose).
2. Dashboard staff have used, with the true/false feedback loop.
3. Readable-capture proof (meter/plate stills) + the choreographed-capture demo.
4. Meter reading ("sale happened" + amount) with accuracy figures; plate + sale↔vehicle link; totalizer feasibility finding.
5. The **before/after pilot review** with real numbers.
6. Data retention & privacy policy.
7. A "what worked best on this site" note + the scoped subscription proposal.

---

*Owner: M. Resolutions · ahsanikram842@gmail.com · 0309 4644574*
