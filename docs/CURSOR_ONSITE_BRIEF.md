# Cursor On-Site Operating Brief — PSO 295-A (Phase 0 gate)

**Paste this whole file to Cursor as its instructions before it does anything on the
station network.** This is a LIVE, RECORDING Dahua NVR on a working fuel forecourt.
The job right now is ONLY the Phase-0 optics-proof gate: prove whether the fixed
camera can see the meter at usable resolution during a real fill. Do NOT build the
reading engine, the state estimator, or any model here.

---

## A. HARD PRECAUTIONS — do not violate (safety, site, device, data)

1. **Physical safety first.** Petrol forecourt: no obstructing nozzles/vehicles, follow
   station staff instructions, keep clear of the pump island during fills.
2. **The NVR is live and recording the real station.** NEVER: reboot it, change its
   recording/storage config, format/clear disks, change network/IP settings, factory
   reset, or update firmware. The disk is already FULL (overwriting oldest) — do not
   add load that risks recording.
3. **Read-only first.** Start with pulling streams/stills only (RTSP + snapshot). Do
   NOT change any camera setting until step B4, and only with station owner consent.
4. **Avoid the admin lockout.** Dahua locks the admin account for ~30 min after a few
   failed logins. So: confirm the password is correct on the FIRST try (test one
   channel), never loop-retry auth, add a short HTTP preflight before hammering, and
   cap retries at 1–2 with backoff. If you see an auth failure, STOP and ask — do not
   retry in a loop.
5. **Record-then-restore any camera change.** Before touching exposure/WDR (`tune_exposure`
   restores auto on exit, but be explicit): read and SAVE the current `VideoInExposure` /
   `VideoInWideDynamicRange` config to a file first; after the sweep, confirm the camera
   is back to its original settings. Leave the site exactly as found.
6. **Credentials never leave `.env`.** Do not print the password to logs/terminal, do not
   hard-code it, do not commit `.env`. `.gitignore` already excludes it — keep it that way.
7. **Privacy — do NOT commit raw footage.** Frames contain faces and plates. Save
   captures under `data/` (already gitignored) ONLY. Never `git add` any `.mp4`/`.jpg`
   of real people. The measurement NUMBERS and a de-identified meter crop are fine to keep.
8. **Do not refactor the existing core.** RTSP ingest, camera control, events, dashboard
   are FROZEN. Integrate against them; if a core change seems needed, write it in
   `docs/FOLLOWUPS.md` and STOP — do not edit core.
9. **Branch, don't push to main.** `git checkout -b onsite/phase0-survey`. Commit
   artifacts (docs, measurements, small tooling) locally. Do not push credentials or footage.
10. **Honesty over optimism.** Report the measured pixels/sharpness/glare exactly. If the
    meter is too small/glary, that is a PASS-worthy *finding* (→ dedicated meter camera),
    NOT a failure to hide or tune around. Never claim a reading the pixels can't support.

---

## B. ACTIONS — ordered runbook (stop at each STOP and report to me)

**B0. Environment sanity (no camera).**
```
python --version            # expect 3.11+
pip install -e '.[dev]' opencv-python-headless -q
pytest -q                   # expect ~59 passed — proves the code is sound before we touch the NVR
```
STOP if pytest is not green.

**B1. Confirm you can reach the NVR (read-only).**
```
ping -c 4 192.168.1.114
```
Expect replies. STOP if not — you're not on the station LAN.

**B2. Set `.env` (one time), then pull ONE channel first (lockout-safe).**
Put in `.env`: `CAM_PUMP_A_HOST=192.168.1.114`, `CAM_PUMP_A_USER=admin`,
`CAM_PUMP_A_PASS=<nvr admin pw>`. Then test a SINGLE channel before scanning all:
```
python -m scripts.nvr_scan --channel 1 --subtype 1
```
- ✅ a still appears under `data/nvr_scan/` → auth + ports are good.
- ❌ auth error / all "no" → WRONG PASSWORD or non-default ports. STOP, do not retry in a
  loop (lockout risk). Report the exact error.

**B3. Scan all channels, find the pump/meter channel.**
```
python -m scripts.nvr_scan --subtype 1
```
Open `data/nvr_scan/*.jpg`, identify the channel whose view includes the dispenser meter.
Record that channel number. STOP and report the table.

**B4. Optics measurement on the meter channel (the actual gate).** With station consent
to briefly change image settings:
```
# first, dump full frames at 4K and read the meter's pixel box off one of them
python -m scripts.tune_exposure --camera pump_a
# then re-run with the meter box to get zoomed crops + sharpness + clip metric:
python -m scripts.tune_exposure --camera pump_a --meter <X> <Y> <W> <H>
```
It saves `current_exposure_config.txt` (the restore point), sweeps auto→fast-shutter→WDR→BLC,
writes `*_meter.jpg` crops, prints sharpness + `MEAN` (clip) per setting, and restores auto
on exit. Confirm the camera returned to its original settings.
STOP and report: the table + the best `*_meter.jpg`.

**B5. Fill the site survey** (`docs/SITE-SURVEY.md`, create if missing) per pilot pump:
display type (7-seg digital vs mechanical wheel), meter pixel size at best exposure,
readable-during-fill? (need a real fill to judge the rolling digits), night lighting,
approx max flow rate, and whether any POS/forecourt-controller feed exists + its protocol.

---

## C. PASS / FAIL decision (record honestly)

- **PASS** = during a live fill, a human can read the meter digits in a `*_meter.jpg`, at
  roughly ≥ 250–300px tall on the amount field (the spec's ~600×300 bar is for the whole
  display). → the meter-reading phases become worth building.
- **FAIL** (expected on a FIXED wide camera — no zoom) = digits too small/glary even at best
  exposure. → deliverable is a HARDWARE line-item: one varifocal / dedicated meter camera
  per pilot pump. This is a legitimate Phase-0 result, not a defeat.

Either way: save the evidence crops, write the finding into the survey, commit on the
branch (NO footage, NO `.env`), and report to me. Do not proceed past Phase 0 without a PASS.

---

## D. If you (Cursor) want to add tooling

Only tiny, additive helpers are allowed here — e.g. a function that prints the meter ROI's
width×height, Laplacian sharpness, and clipped-pixel % from a saved frame. Put new code in
`scripts/` or `src/cameractl/`, never inside the frozen ingest/event/dashboard core, keep it
covered by a quick test, and keep `ruff check` clean. When unsure, STOP and ask.
