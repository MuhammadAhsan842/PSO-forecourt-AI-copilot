"""Milestone 5-6 helper — run detection + tracking + event engine over a saved
video clip. This is how we demo the pipeline without live cameras.

Usage:
    python -m scripts.replay_clip --input tests/fixtures/pump_A_afternoon.mp4 \
                                  --camera ptz1 --annotated out.mp4 --api http://localhost:8080

The annotated output has boxes + track IDs. When ``--api`` is given, emitted
events are POSTed to the real backend so you can watch them stream in on the
dashboard.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

import cv2
import httpx

from src.common.config import get_settings, load_settings_yaml, load_zones
from src.common.logging import get_logger, setup_logging
from src.events.engine import EventEngine, ListSink
from src.inference.detector import Detector
from src.inference.tracker import Tracker

log = get_logger(__name__)


def _draw(frame, tracks):
    for t in tracks:
        b = t.bbox
        cv2.rectangle(frame, (int(b.x1), int(b.y1)), (int(b.x2), int(b.y2)), (0, 255, 0), 2)
        label = f"{t.class_name} #{t.track_id}"
        cv2.putText(
            frame, label, (int(b.x1), max(20, int(b.y1) - 8)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2,
        )
    return frame


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path, help="video file")
    parser.add_argument("--camera", required=True, help="camera id (for zones + logging)")
    parser.add_argument("--annotated", type=Path, help="output annotated mp4")
    parser.add_argument("--api", help="POST emitted events to this base URL")
    parser.add_argument("--every", type=int, default=1, help="run inference every N frames")
    args = parser.parse_args(argv)

    setup_logging(level="INFO", json_output=False)

    settings = get_settings()
    yaml = load_settings_yaml() or {}
    zones = load_zones()

    if not args.input.exists():
        print(f"input not found: {args.input}", flush=True)
        return 2

    detector = Detector(
        weights_path=str(settings.yolo_weights),
        device=settings.device,
        conf_threshold=settings.conf_threshold,
    )
    tracker = Tracker()

    engine = EventEngine(
        enabled_rules=yaml.get("events", {}).get("enabled_rules", []),
        cooldown_seconds=yaml.get("events", {}).get("cooldown_seconds", {}),
        settings={
            "after_hours": zones.after_hours,
            "loitering_seconds": yaml.get("events", {}).get("loitering_seconds", 90),
        },
    )
    cam_zones = zones.cameras.get(args.camera)
    if cam_zones:
        engine.configure_camera(
            args.camera,
            zones_cfg=[z.model_dump() for z in cam_zones.zones],
            lines_cfg=[line.model_dump() for line in cam_zones.lines],
        )
    else:
        log.warning("no_zones_for_camera", extra={"camera_id": args.camera})

    sink = ListSink()
    cap = cv2.VideoCapture(str(args.input))
    if not cap.isOpened():
        print(f"cannot open {args.input}", flush=True)
        return 2

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    writer = None
    if args.annotated:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(args.annotated), fourcc, fps, (w, h))

    frame_idx = 0
    t0 = time.perf_counter()
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame_idx += 1
        if frame_idx % args.every != 0:
            continue

        detections = detector.detect(frame)
        tracks = tracker.update(detections, ts=datetime.utcnow())
        emitted = engine.tick(args.camera, tracks, sink)

        if writer is not None:
            writer.write(_draw(frame, tracks))

        if args.api and emitted:
            _post_events(args.api, emitted)

    dt = time.perf_counter() - t0
    log.info("replay_done", extra={"context": {"frames": frame_idx, "seconds": round(dt, 2), "events": len(sink.events)}})
    print(json.dumps({"frames": frame_idx, "events": len(sink.events), "seconds": round(dt, 2)}))

    cap.release()
    if writer is not None:
        writer.release()
    return 0


def _post_events(base_url: str, events) -> None:
    with httpx.Client(timeout=5.0) as client:
        for ev in events:
            try:
                client.post(f"{base_url.rstrip('/')}/api/v1/events", json=ev.model_dump(mode="json"))
            except Exception as exc:
                log.warning("event_post_failed", extra={"context": {"err": str(exc)}})


if __name__ == "__main__":       # pragma: no cover
    raise SystemExit(main())
