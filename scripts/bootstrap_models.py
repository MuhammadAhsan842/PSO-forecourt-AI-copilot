"""Fetch the base detection weights so M5 detection works out of the box.

The COCO-pretrained YOLO11n already detects the classes we need for the
operational core — car, motorcycle, bicycle, bus, truck, person — so the
reliable week-one alerts (drive-off, after-hours, queue, loitering) run without
any custom training. The dispenser-font digit model and the Pakistani-plate model
are fine-tuned later on on-site frames (M9/M10) and dropped into ``models/``.

    python -m scripts.bootstrap_models            # yolo11n → models/yolo11n.pt
    python -m scripts.bootstrap_models --model yolo11s.pt

Requires the optional inference extra (``pip install -e '.[inference]'``). If it
isn't installed the detector degrades to a no-op and the rest of the system still
runs on saved clips — this script just tells you what's missing.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from src.common.config import get_settings
from src.common.logging import get_logger, setup_logging

log = get_logger(__name__)


def fetch(model: str, dest: Path) -> Path:
    try:
        from ultralytics import YOLO  # type: ignore
    except Exception as exc:
        raise SystemExit(
            "ultralytics not installed. Run: pip install -e '.[inference]'\n"
            f"(underlying error: {exc})"
        ) from exc

    dest.parent.mkdir(parents=True, exist_ok=True)
    # YOLO(model) downloads the weight into the CWD/cache on first use; copy it to
    # the versioned models/ dir the config points at.
    yolo = YOLO(model)
    src = getattr(yolo, "ckpt_path", None) or model
    src_path = Path(src)
    if src_path.exists() and src_path.resolve() != dest.resolve():
        shutil.copy2(src_path, dest)
    log.info("model_ready", extra={"context": {"model": model, "dest": str(dest)}})
    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="yolo11n.pt", help="Ultralytics model name")
    parser.add_argument(
        "--dest", type=Path, default=None, help="output path (default: settings.yolo_weights)"
    )
    args = parser.parse_args(argv)

    setup_logging(level="INFO", json_output=False)
    dest = args.dest or get_settings().yolo_weights
    path = fetch(args.model, dest)
    print(f"weights at {path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
