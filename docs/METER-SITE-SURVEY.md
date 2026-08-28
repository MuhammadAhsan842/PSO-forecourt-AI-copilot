# Meter site survey — one sheet per pump

Fill this **during a live fill**, not idle. Idle LCDs are dark on this site (M1 AMOUNT/LITRES).  
Phase 0 PASS = ROI ≳ **600×300 px** **and** a human can read the rolling digits.  
A FAIL is a hardware line-item, not a reason to lower the gate.

Copy the block below once per pump.

---

## Pump ____  (on-screen label: ______)

**Date / time / lighting:**  
**Filled by (attendant / self):**  
**Product (Hi-Cetane / PMG / …):**  

### 1. Display

- [ ] Seven-segment (bar digits)
- [ ] Graphic LCD (bitmap / blue panel)
- [ ] Mechanical rolling wheels
- [ ] Mixed (describe which field is which): ________________
- **Idle reading shown:** ________
- **Fields visible during fill:** litres / amount / rate / unit price / other: ________
- **Colour of digits / backlight:** ________
- Photo of the bezel kept? path: `data/meter_optics/________________`

### 2. Camera path

| | NVR ch | PTZ? | Preset used | Main-stream (subtype 0) size |
|---|---|---|---|---|
| This attempt | | | | |

- [ ] Channel 9 fixed 4K wide (M1) — expected FAIL on pixel gate
- [ ] Channel 10 PTZ slewed onto this meter (preset index/name: ______)
- [ ] Dedicated meter camera (make/model/IP: ______)
- PTZ can physically see this meter? yes / no / unproven
- After GotoPreset, settle seconds used: ______

### 3. Optics proof run

Command:

```
python -m scripts.meter_optics_proof ...
```

Report path: `data/meter_optics/________________/optics_report.json`

| Metric | Value |
|---|---|
| ROI W×H | |
| `pass_px` | true / false |
| Laplacian sharpness | |
| Glare highlight_frac / p95 | |
| Contrast | |
| `display_guess` | |
| Human-readable during fill? | yes / no |

**Phase 0 verdict:** PASS / FAIL

If FAIL, chosen next hardware: (a) PTZ meter preset on ch10  (b) dedicated meter camera  (c) other: ______

### 4. Night / weather

- Night lighting on the bezel: adequate / glare / unreadable
- Rain / sun angle notes: ________

### 5. Flow / POS (for later phases — record, do not code as fact)

- Observed max L/min this fill (if readable): ______
- Dispenser model: ________
- POS / IFSF / forecourt controller present? yes / no / unknown
- Protocol if known: ________

---

## Site-wide notes (PSO 295-A)

NVR `192.168.1.114`, model DH-NVR5232-4KS3/I, 32ch. Creds in `.env` (`CAM_PUMP_A_*`).  
Password contains `@` — always use `build_nvr_rtsp_url`.  
If HTTP preflight reports `RmLock`, **stop**. Do not retry RTSP until the lock clears.

Known map (2026-08-26):

| NVR ch | On-screen | Notes |
|---|---|---|
| 9 | M1 / Pump 1 | 4K fixed. Pilot. Idle meter ROI ~220×110. |
| 10 | Right Side | 4K PTZ. Preset 2 = overview of pumps 10/4/8, not proven on M1. |
| 1 | M9 / Pump 9 | SD analog. `cameras.yaml` `pump_a.nvr_channel: 1` is this, not M1. |
| 14 | M2 / Pump 2 Hi-Cetane | SD |
| 17 | mosaic | 1920×1080 4×4 of ch 1–16 |
