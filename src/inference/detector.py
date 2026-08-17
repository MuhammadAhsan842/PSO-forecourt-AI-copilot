"""Wrapper around Ultralytics YOLO with graceful fallback.

If ultralytics isn't installed (dev environments without the ML deps),
``Detector.available`` is ``False`` and ``detect()`` returns an empty list —
the pipeline degrades to a no-op rather than crashing. Everything else in
the system works, so tests and offline replay stay green.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from src.common.logging import get_logger
from src.common.types import BoundingBox, Detection

log = get_logger(__name__)

# Ultralytics returns COCO names; we bucket into "vehicle" / "person".
_COCO_VEHICLES = {"car", "motorcycle", "bicycle", "bus", "truck"}


class Detector:
    def __init__(
        self,
        weights_path: str,
        *,
        device: str = "auto",
        conf_threshold: float = 0.35,
        iou_threshold: float = 0.5,
    ):
        self.weights_path = weights_path
        self.device = device
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self._model: Any = None
        self._names: dict[int, str] = {}
        self.available: bool = False
        self._try_load()

    def _try_load(self) -> None:
        try:
            from ultralytics import YOLO  # type: ignore

            self._model = YOLO(self.weights_path)
            self._names = self._model.names or {}
            self.available = True
            log.info(
                "detector_ready",
                extra={"context": {"weights": self.weights_path, "device": self.device}},
            )
        except Exception as exc:
            log.warning(
                "detector_unavailable",
                extra={"context": {"err": str(exc), "weights": self.weights_path}},
            )
            self.available = False

    def detect(self, frame: np.ndarray) -> list[Detection]:
        if not self.available or self._model is None:
            return []
        try:
            results = self._model.predict(
                frame,
                conf=self.conf_threshold,
                iou=self.iou_threshold,
                device=(None if self.device == "auto" else self.device),
                verbose=False,
            )
        except Exception as exc:      # pragma: no cover - inference stability
            log.warning("detector_predict_failed", extra={"context": {"err": str(exc)}})
            return []

        out: list[Detection] = []
        for r in results or []:
            boxes = getattr(r, "boxes", None)
            if boxes is None:
                continue
            for b in boxes:
                try:
                    xyxy = b.xyxy[0].tolist()
                    conf = float(b.conf[0].item())
                    cls_id = int(b.cls[0].item())
                except Exception:
                    continue
                name = self._names.get(cls_id, str(cls_id))
                out.append(
                    Detection(
                        class_id=cls_id,
                        class_name=name,
                        confidence=conf,
                        bbox=BoundingBox(x1=xyxy[0], y1=xyxy[1], x2=xyxy[2], y2=xyxy[3]),
                    )
                )
        return out

    @staticmethod
    def class_is_vehicle(name: str) -> bool:
        return name in _COCO_VEHICLES

    @staticmethod
    def class_is_person(name: str) -> bool:
        return name == "person"
