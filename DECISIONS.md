# Meter pipeline — locked decisions

Token-discipline index. New Phase work does not silently overturn these.

## Phase 0 (2026-08-28)

1. **ONVIF first, Dahua HTTP fallback.** `CameraController.recall_preset` (ONVIF `GotoPreset`) is tried when a preset *name* is given. On this site the cameras sit behind a Dahua NVR; ONVIF against the recorder often cannot address a channel. The fallback that actually moved channel 10 on 2026-08-26 is:

   `http://HOST/cgi-bin/ptz.cgi?action=start&channel=N&code=GotoPreset&arg1=0&arg2=INDEX&arg3=0`

2. **Dashboard live video stays JPEG poll.** Do not put MJPEG in `<img>` tags (Chrome black screen). Processing uses RTSP/OpenCV.

3. **No digit reader on a FAIL crop.** Gate is ≥600×300 px **and** a human can read the digits during a live fill. Pixel gate alone is not enough. Idle ch9 M1 ROI ~220×110 is FAIL; do not “fix” the gate.

4. **Reuse, don’t rewrite.** RTSP URLs go through `build_nvr_rtsp_url` (percent-encodes `@`). Every burst starts with `scripts/nvr_scan._preflight_auth` and aborts on `RmLock`.

5. **Camera-observed ≠ billed.** POS/pump remains source of truth when it exists. Every number later in the pipeline carries confidence + provenance.

6. **Core freeze.** Ingest reconnect, event engine, YOLO/tracker, dashboard shell are not refactored for the meter path. New code lives under `src/meter/` + `scripts/meter_optics_proof.py` + `config/meter/`.

## Phases 1–7 (2026-08-28)

7. **Optics gate still blocks the estimator.** Software now exists for capture→OCR→fusion→Kalman→lifecycle, but a FAIL crop (`pass_px` false) emits `meter_optics_fail`, sets provenance `optics-blocked`, and will not publish `litres_est`. Simulate-fill turns the gate off only because the synthetic renderer is not 600×300.

8. **CNN slot.** `TemplateDigitCnn` is a 12-class nearest-neighbour stand-in (0–9, blank, transitioning) on the existing `render_seven_seg` templates. A trained torch model belongs in `models/meter_7seg/` behind the same `classify_cell` interface.

9. **No invented L/min.** `PumpConfig.max_lpm` is null on this site. The Kalman clamp is unused until you set it in `config/meter/pumps.yaml`.

10. **Additive EventKinds:** `meter_optics_fail`, `meter_fill_start`, `meter_fill_t0`, `meter_fill_stop`, `meter_fill_final`, `meter_needs_review`, `meter_health`. Payload always includes `schema_version`.

11. **POS.** `NullPosAdapter` until a feed exists. Matching tickets flip provenance to `pos-confirmed`. Dashboard never shows a bare number and never marks camera litres as billed.

12. **Live loop is opt-in.** `python -m scripts.meter_run` — the API does not open RTSP on boot. JPEG poll stays the dashboard live path.

13. **Fill contract v2.** Final events carry `T0`, `T_final`, `amount = T_final − T0`, `flags`, `frames_ref`, `schema_version=2`. Anomalies (`meter_unbilled`, `meter_no_vehicle`, `meter_pos_mismatch`) are additive EventKinds. Carry/transition flags are informational; they do not force review.

14. **T0 is the last idle reading**, not the first incrementing frame. Dashboard headline after `final` is `T_final`, not the Kalman mid-fill estimate.
