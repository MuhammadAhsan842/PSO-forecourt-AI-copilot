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
