# On-Site Visit Checklist — PSO 295-A

Goal of the visit: **(1)** see the live camera feeds, **(2)** find the pump/meter
channel and make the meter-readability call (M1/M2 gate), **(3)** leave remote
access behind so you don't have to keep driving out.

The pump is far, so the plan is edge-first (§6): a small computer stays at the
station and does the work; you reach it from home over a VPN. Get that set up on
this visit.

## Take with you

- [ ] Your laptop (Python + this repo already installed — see README Quick Start).
- [ ] **The mini-PC** if you have it (this is the box that stays on-site). If not,
      the laptop gets the data today, but you'll return to install the permanent box.
- [ ] An Ethernet cable (plugging into the NVR's switch/router is more reliable than Wi-Fi).
- [ ] The **NVR admin password** (from the owner / setup records) — the last missing credential.
- [ ] A notebook for the details below.

## At the station — in order

1. **Get on the network.** Connect laptop to the station router (Wi-Fi or Ethernet).
   Confirm you can reach the NVR:
   ```
   ping 192.168.1.114
   ```
   Replies = good. Timeout = you're not on the NVR's network yet.

2. **Grab two NVR screens** (photograph them):
   - **Camera → Remote Device** → camera IPs + which channel is which.
   - **Network → Port** → confirm HTTP/ONVIF = 80, RTSP = 554.

3. **See all the cameras.** In the repo folder terminal:
   ```
   cp .env.example .env          # then set CAM_PUMP_A_HOST=192.168.1.114 and CAM_PUMP_A_PASS=<nvr pw>
   python -m scripts.nvr_scan
   ```
   Open `data/nvr_scan/channel_XX.jpg`, find the pump/meter camera, **note its channel number.**

4. **The readability call (the important one).** Grab the meter channel at full 4K:
   ```
   python -m scripts.nvr_scan --channel <N> --subtype 0
   ```
   Look at the meter in that still. Then, in the **NVR menu → Camera → Image / Exposure**
   for that channel, try:
   - lower **Exposure / faster shutter** (e.g. 1/250 → 1/1000) so the bright display stops glaring,
   - turn **WDR / BLC (backlight)** on,
   re-grab the still after each change, and see whether the **digits become human-readable**.
   - ✅ Readable → the meter reader runs on this camera. Gate passed.
   - ❌ Still too small/glared even with good exposure → flag for a **second, tighter
     camera on the meter** (§13). Note it; don't force it.
   Save the best before/after meter stills — this is the demo that sells PSO.

5. **Leave remote access behind (so you stop driving out).** On the box that stays
   on-site (the mini-PC; temporarily your laptop only proves it works):
   - Install **Tailscale** (https://tailscale.com/download), sign in, note the box's
     Tailscale IP (100.x.x.x).
   - Install Tailscale on your home PC too, same account.
   - From home you can now reach the on-site box (and, once running, its dashboard)
     as if you were local — no router changes, no static IP.

## What to send me after the visit

- The **nvr_scan table** + the **pump channel number**.
- The **before/after meter stills** from step 4.
- The two NVR screens from step 2 (ports + camera list).

With the channel confirmed I lock it into `config/cameras.yaml`, and with the meter
stills we make the M9 go/no-go call honestly.

## Reality check

- You can absolutely get the **live feed on your laptop at the station today.**
- **Remote** access from home needs one device left running on-site — that's the
  mini-PC. A laptop visit gets the data; the permanent box gets you ongoing access.
- Don't stream raw 4K to your home office continuously — it's heavy and laggy (§6).
  Process on-site; view the dashboard remotely.
