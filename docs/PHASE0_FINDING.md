# Phase 0 Finding & Next Steps — PSO 295-A

**Date:** on-site survey · **Camera under test:** channel 9 = Pump 1 (Hi-Cetane),
Dahua fixed 8MP bullet behind DHI-NVR5216-EI.

## Result: meter OCR is NOT feasible on the existing wide camera (hardware gap)

Measured on the live 4K stream:

| Metric | Measured | Needed for a reader | Verdict |
|---|---|---|---|
| Meter ROI (native) | 220 × 110 px | ≥ ~600 × 300 px | ❌ |
| Amount-field height (native) | ~110 px | ~250–300 px | ❌ |
| Glare (highlight fraction) | 0.06 (mild) | — | ✅ not the blocker |
| Idle "0000" legible after 5× digital zoom | yes | — | ⚠️ not a reader PASS |

**Root cause is optical resolution, not glare or software.** The camera is fixed (no
optical zoom); the meter is too few pixels at source. Digital zoom / enhancement cannot
manufacture digits that were never captured. Exposure/WDR tuning was therefore not the
fix. This is the plan's anticipated Phase-0 FAIL branch (§0, §3, §13), not a defeat.

## Hardware line-item to close the gap

One **dedicated meter camera per pilot pump**, framed tight on the dispenser display:

- **~2.5–3× tighter framing** than the current wide view (110px → ~275px amount field).
- **Varifocal or optical-zoom** bullet (e.g. 2.7–12 mm motorized varifocal, ≥2MP is plenty
  for a tight crop), WDR, IR/warm illumination for night.
- Mounted ~1.5–3 m from the dispenser with a clear, square-on line to the display.
- Fed into a spare channel on the existing NVR (16ch, ~4 free) — no new recorder needed.
- Start with **one pump** to prove the reader, then replicate.

Once installed, re-run Phase 0 on that camera; a PASS unlocks the meter-reading phases.

## What DOES work on the existing cameras today (ship this now)

Meter reading is the ONLY capability that needs new hardware. The operational core runs on
the current wide 4K cameras immediately:

- Vehicle-at-pump / dwell, **drive-off**, **after-hours presence**, queue/loitering,
  restricted-area — all already built and tested in this repo.
- The NVR's own **AcuPick** (licensed: Human Body + Motor Vehicle) can supply or corroborate
  detection, reducing GPU need.
- Plate reading is viable where a camera angle catches plates (separate from the meter issue).

**Recommended sequencing:** deploy the operational alerts + dashboard on existing cameras
for week-one value while the meter camera(s) are procured and installed.

## Commercial framing (important)

Per the meter-reading spec, the camera meter reading is a **verification/assurance layer with
confidence**, never the billed source of truth — the calibrated pump/POS is. Ask PSO whether a
**POS / forecourt-controller feed** exists: if so, the meter camera becomes a cross-check for
unbilled-dispense / drive-off-with-amount, which is the highest-value use and needs only
"good enough to flag," not perfect digits.

## Still to gather on-site (for the proposal)

- [ ] Full 16-channel map (which channel sees which pump/area) — read-only `nvr_scan`.
- [ ] Mounting options + distance for a tight meter camera per pilot pump.
- [ ] Night look at the meter (LCD bloom after dark?).
- [ ] POS/controller feed: exists? brand/protocol?
- [ ] One clean full-res idle still per pilot pump meter (evidence; keep local, do not commit).
