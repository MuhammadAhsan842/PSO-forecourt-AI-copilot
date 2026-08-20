"""Choreographed capture sequencer (M8): priority order + one-PTZ constraint."""

from __future__ import annotations

import numpy as np

from src.capture.sequencer import CaptureSequencer, CaptureStage


class _FakeController:
    def __init__(self, fail_on: set[str] | None = None):
        self.recalled: list[str] = []
        self._fail_on = fail_on or set()

    def recall_preset(self, token: str) -> None:
        from src.cameractl.controller import ControlError

        if token in self._fail_on:
            raise ControlError(f"preset {token} unreachable")
        self.recalled.append(token)


def _sharp_frame() -> np.ndarray:
    # High-frequency checkerboard → high Laplacian variance (sharp).
    f = np.indices((80, 80)).sum(axis=0) % 2 * 255
    return np.stack([f, f, f], axis=-1).astype(np.uint8)


def _blurry_frame() -> np.ndarray:
    return np.full((80, 80, 3), 128, dtype=np.uint8)


def test_meter_wins_first_then_plate() -> None:
    ctrl = _FakeController()
    seq = CaptureSequencer(
        ctrl,
        preset_tokens={"meter": "10", "plate": "11", "occupant": "12"},
        latest_frame=_sharp_frame,
        settle_seconds=0,
        min_sharpness=10.0,
    )
    results = seq.run()
    stages = [r.stage for r in results]
    # Overview first, then meter (money) before plate — the priority order.
    assert stages[0] == CaptureStage.OVERVIEW
    assert stages.index(CaptureStage.METER) < stages.index(CaptureStage.PLATE)
    assert all(r.ok for r in results if r.stage != CaptureStage.OVERVIEW)


def test_blurry_capture_is_flagged_not_dropped() -> None:
    seq = CaptureSequencer(
        _FakeController(),
        preset_tokens={"meter": "10"},
        latest_frame=_blurry_frame,
        settle_seconds=0,
        min_sharpness=1000.0,  # nothing will pass
        priority=[CaptureStage.METER],
    )
    meter = next(r for r in seq.run() if r.stage == CaptureStage.METER)
    assert meter.ok is False
    assert meter.frame is not None  # kept for the reviewer
    assert "sharpness" in (meter.reason or "")


def test_preset_recall_failure_is_captured_not_raised() -> None:
    seq = CaptureSequencer(
        _FakeController(fail_on={"10"}),
        preset_tokens={"meter": "10"},
        latest_frame=_sharp_frame,
        settle_seconds=0,
        priority=[CaptureStage.METER],
    )
    meter = next(r for r in seq.run() if r.stage == CaptureStage.METER)
    assert meter.ok is False
    assert "unreachable" in (meter.reason or "")
