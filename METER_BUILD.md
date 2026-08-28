# Meter-reading pipeline — architecture map

**Status:** Phase map only. No reader engine until **Phase 0 PASS** on at least the pilot pump.  
**Design source:** Cursor spec (2026-08-28) plus on-site notes from 2026-08-26.  
**Missing file:** `PSO_Meter_Reading_Pipeline.md` is **not in this repo**. This map treats the pasted Cursor spec as the design rationale until that file is added.

**Stance (frozen):** camera-derived litres/rupees are **camera-observed**, never billed truth. Every number carries confidence + provenance. Low confidence → human review, never silent trust.

---

## 1. Existing structure (real paths)

Repo root: `pso-surveillance/`. Do not refactor these cores; plug in.

### 1.1 Config & secrets

| Path | Role |
|---|---|
| `config/cameras.yaml` | Camera roster. `pump_a` is NVR-fronted (`nvr_channel`, `subtype`, `host_env`). **Stale:** still `nvr_channel: 1`; on-site M1 is **channel 9**. |
| `config/presets.yaml` | Named PTZ presets (`ptz1.overview`, `pump_a_meter`, …). Placeholder pan/tilt/zoom — not the live ch10 preset 2. |
| `config/zones.yaml` | Pump-bay / queue polygons for the event engine. |
| `config/settings.yaml` | Inference FPS, CORS, capture sharpness threshold. |
| `.env` / `.env.example` | `CAM_PUMP_A_HOST/USER/PASS` — credentials stay here, never in YAML. |

### 1.2 Camera / PTZ / RTSP (hard-won — do not re-break)

| Path | Plug-in |
|---|---|
| `src/common/config.py` → `build_nvr_rtsp_url()` | Percent-encodes `@` in passwords. **Reuse.** |
| `scripts/nvr_scan.py` → `_preflight_auth()` | HTTP digest preflight; aborts on `RmLock`. **Reuse** before any burst of RTSP. |
| `src/cameractl/controller.py` | `CameraController`: ONVIF `GotoPreset` (`recall_preset`), `save_preset`, `move_absolute`, `list_presets`. |
| `src/cameractl/dahua_http.py` | Dahua CGI: exposure/WDR/snapshot. Imaging often **fails on NVR:80** (needs camera vhost port). |
| `src/cameractl/capabilities.py` | M1 probe matrix (exposure vs PTZ+focus). |
| `src/ingest/worker.py` | `IngestWorker`: reconnect, latest-frame-wins, `FrameSample(camera_id, ts, frame, seq)`. **Reuse for Phase 1 grabber.** |
| `src/capture/sequencer.py` | Triggered capture: overview → meter preset → plate. `frame_sharpness()` (Laplacian). |
| `scripts/tune_exposure.py` | Exposure/WDR sweep + meter crop. |
| `src/api/routes/nvr.py` | Dashboard live: JPEG poll (not MJPEG — Chrome black screen). Hard-coded `_METER_ROI[9] = (1800, 700, 220, 110)` on 3840×2160. |

**On-site fact (2026-08-26):** NVR `192.168.1.114`, model **DH-NVR5232-4KS3/I** (docs still say 5216). Channel 10 is a real PTZ; channel 9 is a **fixed 4K** (`ElectricFocus=false`). PTZ CGI `GotoPreset` via `ptz.cgi` worked on ch10 (preset 1 “3hree machine”, preset 2 saved as overview).

### 1.3 Detection, events, linking

| Path | Plug-in |
|---|---|
| `src/inference/detector.py` | YOLO wrapper. |
| `src/inference/tracker.py` | IoU tracker. |
| `src/events/engine.py` | `EventEngine` + `EventSink.emit(EventRecord)`. |
| `src/events/rules.py` | `vehicle_settled_at_pump`, dwell, drive-off, etc. |
| `src/link/associator.py` | `SaleAssociator` — sale ↔ vehicle visit. **Phase 6 consumes this.** |
| `src/link/transactions.py` | Drive-off / amount attach. |
| `src/common/types.py` | `EventKind`, `EventRecord`. Meter events should **extend kinds**, not hijack existing ones. |

### 1.4 OCR (skeleton — not the Phase 2 engine)

| Path | What it is today |
|---|---|
| `src/ocr/seven_seg.py` | Classical SSOCR-style segment reader + synthetic renderer. Natural Phase 2 baseline. |
| `src/ocr/meter.py` | `DigitClassifier` protocol, `NotReadyClassifier`, `majority_vote_digits`, `arithmetic_check`, `MeterSaleState` idle→counting→settled. **Extend, don’t replace the protocol.** |
| `src/ocr/plate.py` / `plate_pk.py` | Plate path — out of meter-pipeline scope. |

### 1.5 Backend / dashboard / storage

| Path | Plug-in |
|---|---|
| `src/api/main.py` | FastAPI app, CORS, routers, `/ws/events`. |
| `src/api/routes/events.py` | `GET/POST /api/v1/events` + WebSocket broadcast. |
| `src/api/websocket.py` | `broadcast_event()`. |
| `src/storage/models.py` | `EventRow`, `FeedbackRow`, **`ReadingRow`** (`kind=meter\|plate`, `value`, `confidence`, `payload` JSON). |
| `src/storage/repository.py` | Persistence helpers. |
| `src/storage/retention.py` | Snapshot/DB purge — meter frame refs must obey this. |
| `dashboard/src/App.tsx` | Shell. |
| `dashboard/src/components/CinemaStage.tsx` | M1 4K cinema + loupe (HQ JPEG poll). |
| `dashboard/src/components/LiveZoom.tsx` | Live JPEG poll (do not switch UI back to MJPEG). |
| `dashboard/src/components/NvrGrid.tsx` | Channel grid. |
| `dashboard/src/components/EventLog.tsx` | Feedback true/false. **Phase 7 review queue extends this pattern.** |

### 1.6 Exact plug-in points (new code lives here)

| New (planned) | Talks to |
|---|---|
| `src/meter/` package | Isolated pipeline. Imports `IngestWorker`, `CameraController`, `EventSink`, `ReadingRow`. |
| `config/meter/` | Versioned ROI/presets/thresholds (not edited into `nvr.py`). |
| `scripts/meter_optics_proof.py` | Phase 0 tooling only. |
| `src/api/routes/meter.py` | Readings + health; does **not** replace `/events`. |
| Dashboard: meter panel | Confidence badge + provenance; never a bare number. |

---

## 2. Per-phase module plan

Work stops after each phase until you confirm.

### Phase 0 — Optics proof (tooling only; you run on-site)

**Do not build the estimator.** Deliver:

| Module | Path |
|---|---|
| PTZ goto named preset | `scripts/meter_optics_proof.py` using `CameraController.recall_preset` + Dahua `ptz.cgi?code=GotoPreset` fallback |
| 4K main-stream burst | same script; `build_nvr_rtsp_url(..., subtype=0)` + preflight |
| Auto-measure report | pixel size of meter ROI, Laplacian sharpness, glare/contrast, 7-seg vs wheel heuristic |
| Site-survey checklist | `docs/METER-SITE-SURVEY.md` (one sheet per pump) |

**Gate:** PASS if during a **live fill** the meter ROI is ≳ **600×300 px** and a human can read digits.  
**On-site preview (ch9 M1 idle, 2026-08-26):** ROI ~**220×110** on 3840×2160 — **would FAIL this gate**. Ch10 PTZ is the only optical-zoom candidate unless we add a dedicated meter cam.

### Phase 1 — Capture, ROI, segmentation, calibration

| Module | Path |
|---|---|
| Grabber (reconnect/watchdog/ts) | wrap `src/ingest/worker.py`; do not fork a second RTSP stack |
| ROI calibration UI | dashboard tool + `config/meter/roi/<pump>_<preset>.vN.yaml` |
| Registration | `src/meter/register.py` (phase correlation / bezel template) |
| Digit cells | `src/meter/segment.py` (reuse geometry ideas from `seven_seg.py`) |
| Change-rate labels | `src/meter/change_rate.py` |
| Health events | emit via `EventSink` — new `EventKind`s (propose, don’t silently add) |

`METER_BUILD.md` (this file) + `DECISIONS.md` stay the token-discipline index.

### Phase 2 — Per-frame 7-seg OCR

| Module | Path |
|---|---|
| SSOCR baseline | `src/ocr/seven_seg.py` (existing) behind `DigitClassifier` |
| CNN 0–9 + blank + transitioning | `src/meter/ocr_cnn.py` + `models/meter_7seg/` |
| Synthetic renderer | already in `seven_seg.py` (`render_seven_seg`) — extend, don’t duplicate |
| Temperature scaling | `src/meter/calibrate.py` |

### Phase 3 — Multi-frame fusion

| Module | Path |
|---|---|
| Static cell average | `src/meter/fusion.py` |
| No fusion on rolling cells | enforced here + estimator |

### Phase 4 — Monotonic state estimator

| Module | Path |
|---|---|
| State `x = [T, r]` | `src/meter/estimator.py` (`filterpy` Kalman or particle filter) |
| Physical max L/min | config, not code constants |

### Phase 5 — Fill lifecycle + event contract

| Module | Path |
|---|---|
| Start / T0 / stop / T_final | `src/meter/lifecycle.py` (evolve `MeterSaleState` in `meter.py`) |
| Versioned event | persist `ReadingRow` + `EventRecord` payload `schema_version` |
| Frame refs + retention | `src/storage/snapshots.py` + existing retention |

### Phase 6 — Correlation / POS hook

| Module | Path |
|---|---|
| CV ↔ meter link | `src/link/associator.py` + `src/meter/correlate.py` |
| POS adapter (stub OK) | `src/meter/pos.py` — interface even with no feed |

### Phase 7 — Scale / ops / security

| Module | Path |
|---|---|
| Pump→camera/preset map | `config/meter/pumps.yaml` |
| PTZ scheduler | `src/meter/scheduler.py` |
| Supervisor / health API | `src/api/routes/meter.py` |
| Dashboard: confidence, review queue, ops | extend React; JPEG poll only |

---

## 3. Numbered assumptions — confirm or correct

1. **Pilot pump is M1 (pump 1), NVR channel 9**, not `cameras.yaml` `pump_a.nvr_channel: 1` (that channel is labelled M9 on site).
2. **Phase 0 on ch9 as-is will FAIL the ≥600×300 optical gate.** Next hardware choice is either (a) slew **channel 10 PTZ** onto M1’s meter during a fill, or (b) a dedicated fixed/varifocal meter camera. The reader is not built on the wide 220×110 crop.
3. **Display type on M1:** green 4-digit window (idle `0000`) plus a **blue AMOUNT/LITRES/RATE LCD** that is dark when idle. Unconfirmed whether the live fill uses 7-seg, a graphic LCD, or both. Survey must record this **during a fill**.
4. **Channel 10 PTZ can or cannot see pump 1’s meter** — unproven. Overview preset showed pumps 10/4/8, not M1. Phase 0 must try a meter preset before buying a new cam.
5. **No POS / IFSF / forecourt-controller feed is connected today.** Phase 6 ships a stub adapter; POS remains source of truth when it appears.
6. **Max flow rate** for estimator ceiling is unknown (typical PSO dispenser ~40–50 L/min diesel — **not to be coded as fact** until you confirm).
7. **NVR credentials** stay in `.env` (`CAM_PUMP_A_*`). Password contains `@`; all RTSP URLs must go through `build_nvr_rtsp_url`.
8. **UI live video** stays JPEG-poll / cinema stage. Processing uses raw RTSP/OpenCV. We will not put MJPEG in `<img>` tags.
9. **`EventKind` / API schema** may gain meter-specific kinds and a versioned fill event; that is an additive change we will propose before editing `types.py`.
10. **`PSO_Meter_Reading_Pipeline.md`** will be added to repo root or the Cursor spec remains the rationale.
11. **Legal stance:** no camera number is billed; dashboard always shows `camera-observed` vs `POS-confirmed` + confidence tier.
12. **Core freeze:** ingest reconnect, URL-encoding, HTTP preflight, event engine, YOLO/tracker, and dashboard shell are not refactored “for cleanliness.” Meter code lives under `src/meter/` + scripts/config listed above.

---

## 4. Phase 0 tooling — delivered

Run on the station LAN (or VPN) **during a live fill**. Do not build the reader until you report PASS.

```bash
# M1 / ch9 fixed wide — expected FAIL on the 600×300 pixel gate
python -m scripts.meter_optics_proof --channel 9 --no-ptz --burst 20 \
    --roi 1800 700 220 110 --out data/meter_optics/m1_ch9

# List PTZ presets on channel 10
python -m scripts.meter_optics_proof --channel 10 --list-presets --burst 0

# After you save a meter-aimed preset on ch10, slew then burst (change ROI by eye)
python -m scripts.meter_optics_proof --channel 10 --preset-index 2 --settle 6 --burst 30 \
    --roi 1800 700 400 250 --out data/meter_optics/m1_via_ch10_ptz
```

Host/user/password default from `.env` (`CAM_PUMP_A_*`). Override with `--host --user --password`. Exit 8 = pixel-gate FAIL (frames still written). Fill `docs/METER-SITE-SURVEY.md` and set `human_readable_during_fill` in the JSON after you watch the fill.

**Stop here.** Reply **PASS** or **FAIL** for the pilot pump. FAIL + ch10 cannot see M1 → dedicated meter camera, not a reader on 220×110.
