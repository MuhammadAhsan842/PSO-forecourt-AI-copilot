"""Meter-reading pipeline. Phase 0 = optics only; no digit reader here."""

from .optics import GATE_MIN_H, GATE_MIN_W, optics_report

__all__ = ["GATE_MIN_H", "GATE_MIN_W", "optics_report"]
