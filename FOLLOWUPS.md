# Meter pipeline follow-ups

The spec is implemented as software. These items are **not** silently in scope — they wait on site, hardware, or a later explicit request.

1. **Phase 0 PASS** on a live fill at M1. Ch9 idle crop ~220×110 fails the ≥600×300 gate. Do not treat the wide cam as the reader. Next hardware: ch10 PTZ meter preset or a dedicated meter camera.
2. **Held-out real fills** for disaggregated metrics (final-total vs mid-fill digits, day vs night, reliability diagram). Synthetic fills are bootstrap only.
3. **PyTorch CNN weights** in `models/meter_7seg/` trained on synthetic + auto-labelled real frames. Slot is `TemplateDigitCnn` / `classify_cell` until then.
4. **POS / IFSF feed.** `NullPosAdapter` is the hook. Unbilled/mismatch flags stay honest while this is empty.
5. **Dashboard/API auth** and least-privilege NVR account — site security, not a code secret.
6. **filterpy** was not added; the 2-state Kalman in `estimator.py` is the estimator. Swap only if a particle filter is required for discrete digits.
7. **Edge load budget** on the on-site box (CPU/GPU/memory per stream) — measure on the station hardware.
8. `PSO_Meter_Reading_Pipeline.md` is still missing from the repo; this spec + `METER_BUILD.md` + `DECISIONS.md` are the rationale.
