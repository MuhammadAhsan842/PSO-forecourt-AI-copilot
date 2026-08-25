# Site Notes — PSO 295-A, Airlines Society, Lahore

Live findings from on-site device discovery. Feeds the §14 handover ("what worked
best on this site") and the M1–M3 gate planning. Update as we learn more.

## Topology (as discovered)

```
[Dahua cameras ~16]  --PoE-->  [Dahua NVR: DHI-NVR5216-EI @ 192.168.1.114]  --LAN-->  [our mini-PC]
   fixed 8MP bullets                16ch, all 3840x2160 (4K)                     RTSP pull by channel
   e.g. DH-IPC-HFW1839TC-A-IL       AcuPick AI: Human Body + Motor Vehicle
```

**We integrate with the NVR, not the cameras directly.** Streams are pulled from
the recorder by channel: `rtsp://admin:PASS@192.168.1.114:554/cam/realmonitor?channel=N&subtype=0`
(subtype 0 = main 4K, 1 = lighter sub-stream). Config models this via
`nvr_channel` on the `pump_a` camera (see `config/cameras.yaml`).

## Device facts

| Item | Value | Source |
|---|---|---|
| NVR model | DHI-NVR5216-EI (16ch) | NVR Version screen |
| NVR IP (LAN1) | 192.168.1.114 | NVR Network screen |
| NVR MAC | 98:f9:cc:89:1b:66 | NVR Network screen |
| System / Web version | V5.001.0000000.2.R / V5.22.0.260326.4303490 | NVR Version |
| ONVIF server | 25.06 (V3.1.0.2322951) | NVR Version |
| Channels | 16, all 4K (3840×2160) | NVR Camera/Version |
| On-box AI | AcuPick — Human Body + Motor Vehicle, License Normal | NVR AI screen |
| Camera model | DH-IPC-HFW1839TC-A-IL (fixed 8MP bullet) | camera Device Info |

Credentials live only in `.env` (NVR IP + admin creds). Never committed.

## Implications for the build

1. **Detection can potentially be offloaded to the NVR.** AcuPick already does
   Human Body + Motor Vehicle detection natively. Option A (plan default): run our
   own YOLO11 + ByteTrack on pulled RTSP. Option B: consume the NVR's AI
   events/metadata (ONVIF events / Dahua SDK) and keep only our event engine
   (zones, dwell, drive-off, meter-link) on top. **B could remove the GPU
   requirement** for the operational core. To evaluate during M4/M5 — do NOT
   switch the architecture before measuring event granularity and latency from
   the NVR. Our detector already degrades gracefully, so both paths coexist.

2. **Meter/plate readability (M1/M2) is still the gating question, and harder
   here.** The camera is FIXED (no zoom/focus), so exposure/shutter/WDR is the
   only lever. Two extra wrinkles from the NVR:
   - Exposure may need to be set **on the camera via the NVR's Remote Device →
     camera config** menu, not over ONVIF to the NVR.
   - Reaching the camera's own web/ONVIF directly may require the NVR's
     "virtual host / passthrough" feature (cameras sit on the NVR's internal PoE
     subnet, not the main LAN).
   If exposure tuning can't make the ~30px meter digits human-readable on the 4K
   wide view, that's the plan's documented "flag as client-side dependency" →
   a second, tighter-mounted camera aimed at the meter (§13, M12).

3. **⚠️ NVR disk is FULL.** 7.18 TB at 0.00 MB free, Health "Normal" — it is
   overwriting oldest footage. Not urgent, but flag to the client: any historical
   footage we might want for training/validation is being aged out continuously,
   so capture baseline clips early (M4 `capture_baseline.py`).

## Open items (need two more NVR screens + one credential)

- **Camera IPs / confirm channel mapping** — NVR: *Camera → Remote Device*.
- **Ports** — NVR: *Network → Port* (confirm HTTP/ONVIF 80, RTSP 554).
- **NVR admin password** — from the site's setup records.
