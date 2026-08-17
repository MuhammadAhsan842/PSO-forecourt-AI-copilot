"""Milestone 1 — Camera-control probe.

Usage:
    python -m scripts.camera_probe                 # probes every camera in cameras.yaml
    python -m scripts.camera_probe --camera ptz1   # one camera
    python -m scripts.camera_probe --json          # machine-readable output

Prints a capability matrix per camera and returns non-zero if the M1 GATE fails
on any configured camera. This is the demo you show live to prove which
controls the API exposes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.cameractl.capabilities import probe_camera
from src.common.config import CameraConfig, load_cameras
from src.common.logging import get_logger, setup_logging

log = get_logger(__name__)


def _probe_one(cam: CameraConfig) -> dict:
    caps = probe_camera(
        cam.id,
        host=cam.host,
        onvif_port=cam.onvif_port,
        user=cam.user,
        password=cam.password,
        rtsp_url=cam.rtsp_url or None,
    )
    return {"camera": cam.id, "gate_passes": caps.gate_passes(), "capabilities": caps.to_dict(), "summary": caps.readable_summary()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Probe camera capabilities (Milestone 1).")
    parser.add_argument("--camera", help="probe just this camera id")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--output", type=Path, help="write full report to this file")
    args = parser.parse_args(argv)

    setup_logging(level="INFO", json_output=False)

    cameras = load_cameras()
    if args.camera:
        cameras = [c for c in cameras if c.id == args.camera]
        if not cameras:
            print(f"no camera with id={args.camera}", file=sys.stderr)
            return 2

    if not cameras:
        print("no cameras configured", file=sys.stderr)
        return 2

    reports = [_probe_one(cam) for cam in cameras]

    if args.json or args.output:
        payload = json.dumps(reports, indent=2, default=str)
        if args.output:
            args.output.write_text(payload)
        if args.json:
            print(payload)
    else:
        for rep in reports:
            print("=" * 72)
            print(rep["summary"])
            print(f"  GATE: {'PASS' if rep['gate_passes'] else 'FAIL'}")

    any_fail = any(not r["gate_passes"] for r in reports)
    if any_fail:
        print(
            "\nGATE FAILED for at least one camera.\n"
            "Per .cursorrules: STOP and escalate — meter/plate scope must be renegotiated.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":       # pragma: no cover
    raise SystemExit(main())
