"""Choreographed capture — the transaction sequence (Milestone 8).

Trigger: a `VEHICLE_SETTLED_AT_PUMP` event from the engine.
Sequence:  overview snapshot -> METER preset (sharp still) -> PLATE preset (on exit)
           -> OCCUPANT (best effort).

Priority order enforces the one-PTZ constraint from the .cursorrules:
  the sequencer ALWAYS wins the meter first, then the plate. Occupant is dropped
  if we run out of dwell time.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

import numpy as np

from src.cameractl.controller import CameraController, ControlError
from src.common.logging import get_logger

log = get_logger(__name__)


class CaptureStage(str, Enum):
    OVERVIEW = "overview"
    METER = "meter"
    PLATE = "plate"
    OCCUPANT = "occupant"


@dataclass
class CaptureResult:
    stage: CaptureStage
    ok: bool
    frame: np.ndarray | None
    sharpness: float | None
    reason: str | None = None


def frame_sharpness(frame: np.ndarray) -> float:
    """Laplacian variance — higher means sharper."""
    try:
        import cv2

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())
    except Exception:      # pragma: no cover - only if cv2 missing
        return 0.0


class CaptureSequencer:
    """Runs one full pump-visit capture. Blocking (called from a task/thread)."""

    def __init__(
        self,
        controller: CameraController,
        preset_tokens: dict[str, str],
        latest_frame: Callable[[], np.ndarray | None],
        *,
        settle_seconds: float = 1.2,
        min_sharpness: float = 80.0,
        priority: list[CaptureStage] | None = None,
    ):
        self.controller = controller
        self.preset_tokens = preset_tokens
        self.latest_frame = latest_frame
        self.settle_seconds = settle_seconds
        self.min_sharpness = min_sharpness
        self.priority = priority or [CaptureStage.METER, CaptureStage.PLATE, CaptureStage.OCCUPANT]

    def run(self) -> list[CaptureResult]:
        """Execute the sequence. Never raises: any failure is captured on the result."""
        results: list[CaptureResult] = []
        results.append(self._grab(CaptureStage.OVERVIEW))
        for stage in self.priority:
            results.append(self._grab(stage))
        return results

    def _grab(self, stage: CaptureStage) -> CaptureResult:
        token = self.preset_tokens.get(stage.value)
        if not token and stage != CaptureStage.OVERVIEW:
            return CaptureResult(
                stage=stage, ok=False, frame=None, sharpness=None, reason="preset not defined"
            )

        if token:
            try:
                self.controller.recall_preset(token)
            except ControlError as exc:
                return CaptureResult(
                    stage=stage, ok=False, frame=None, sharpness=None, reason=str(exc)
                )
            time.sleep(self.settle_seconds)

        frame = self.latest_frame()
        if frame is None:
            return CaptureResult(
                stage=stage, ok=False, frame=None, sharpness=None, reason="no frame"
            )

        sharp = frame_sharpness(frame)
        ok = sharp >= self.min_sharpness or stage == CaptureStage.OVERVIEW
        # Keep the frame either way — the reviewer wants to see even the
        # not-sharp-enough one; ok/sharpness/reason tells them why we flagged it.
        return CaptureResult(
            stage=stage,
            ok=ok,
            frame=frame,
            sharpness=sharp,
            reason=None if ok else f"sharpness {sharp:.1f} < {self.min_sharpness}",
        )
