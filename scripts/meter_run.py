"""Live meter loop on the station LAN. Does not start from the API process.

python -m scripts.meter_run --pump m1
"""

from __future__ import annotations

import argparse
import time
from datetime import UTC, datetime

from scripts.nvr_scan import _preflight_auth
from src.common.config import load_cameras
from src.common.logging import get_logger, setup_logging
from src.meter.config import load_pumps
from src.meter.grabber import MeterGrabber
from src.meter.supervisor import MeterSupervisor

log = get_logger(__name__)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Run the meter pipeline on live NVR frames")
    p.add_argument("--pump", default="m1")
    p.add_argument("--fps", type=float, default=4.0)
    args = p.parse_args(argv)
    setup_logging(level="INFO", json_output=False)

    pumps = [x for x in load_pumps() if x.id == args.pump and x.enabled]
    if not pumps:
        print(f"no enabled pump {args.pump}", flush=True)
        return 2
    pump = pumps[0]
    cams = {c.id: c for c in load_cameras()}
    cam = cams.get(pump.camera_id)
    if cam is None:
        print(f"camera {pump.camera_id} missing from cameras.yaml", flush=True)
        return 3
    cam = cam.model_copy(update={"nvr_channel": pump.nvr_channel, "subtype": 0})
    if cam.host and cam.user and cam.password:
        ok, msg = _preflight_auth(cam.host, cam.user, cam.password)
        if not ok:
            print(f"preflight FAILED: {msg}", flush=True)
            return 4
        print(f"preflight OK: {msg}", flush=True)

    grab = MeterGrabber(cam, target_fps=max(1, int(args.fps)))
    sup = MeterSupervisor(pumps)
    grab.start()
    try:
        period = 1.0 / max(args.fps, 0.5)
        while True:
            sample = grab.latest()
            if sample is None or grab.stale():
                sup.note_stale(pump.id, datetime.now(UTC))
                time.sleep(period)
                continue
            tick = sup.process_frame(pump.id, sample.frame, sample.ts)
            print(
                f"{tick.fill_phase:8} {tick.provenance:16} "
                f"L={tick.litres_est} raw={tick.litres_raw!r} "
                f"tier={tick.confidence_tier} optics={tick.optics_pass}",
                flush=True,
            )
            time.sleep(period)
    except KeyboardInterrupt:
        return 0
    finally:
        grab.stop()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
