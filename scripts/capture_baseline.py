"""Milestone 4 helper — capture day/night baseline stills from each camera.

Runs the ingest workers for a wall-clock window, grabs snapshots every
``--interval`` seconds, and drops them under ``data/baseline/<camera>/<label>/``.
Use this once during the day and once at night to seed the readability review
in M2.
"""

from __future__ import annotations

import argparse
import time
from datetime import datetime
from pathlib import Path

import cv2

from src.common.config import get_settings, load_cameras
from src.common.logging import get_logger, setup_logging
from src.ingest.worker import IngestWorker

log = get_logger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="day", help="folder name suffix (day/night/...)")
    parser.add_argument("--duration", type=int, default=60, help="seconds to capture")
    parser.add_argument("--interval", type=float, default=5.0, help="snapshot interval s")
    parser.add_argument("--camera", help="only this camera id")
    args = parser.parse_args(argv)

    setup_logging(level="INFO", json_output=False)

    cams = load_cameras()
    if args.camera:
        cams = [c for c in cams if c.id == args.camera]
    if not cams:
        print("no cameras configured", flush=True)
        return 2

    root = Path("./data/baseline")
    workers: list[IngestWorker] = []
    for cam in cams:
        workers.append(IngestWorker(cam, target_fps=cam.fps))
    for w in workers:
        w.start()

    started_at = time.time()
    next_save = started_at
    log.info(
        "baseline_start",
        extra={"context": {"label": args.label, "duration": args.duration, "n_cameras": len(cams)}},
    )

    try:
        while time.time() - started_at < args.duration:
            time.sleep(0.1)
            if time.time() < next_save:
                continue
            next_save = time.time() + args.interval
            for w in workers:
                sample = w.latest()
                if sample is None:
                    continue
                out_dir = root / w.camera.id / args.label
                out_dir.mkdir(parents=True, exist_ok=True)
                stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
                out = out_dir / f"{stamp}.jpg"
                cv2.imwrite(str(out), sample.frame)
                log.info("baseline_frame_saved", extra={"camera_id": w.camera.id, "context": {"path": str(out)}})
    finally:
        for w in workers:
            w.stop()

    print(f"baseline saved under {root.resolve()}")
    _ = get_settings()
    return 0


if __name__ == "__main__":       # pragma: no cover
    raise SystemExit(main())
