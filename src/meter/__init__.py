"""Meter-reading pipeline. Optics FAIL still blocks billed-looking numbers."""

from .optics import GATE_MIN_H, GATE_MIN_W, optics_report
from .pipeline import FILL_SCHEMA_VERSION, MeterPipeline, MeterTick
from .supervisor import MeterSupervisor

__all__ = [
    "FILL_SCHEMA_VERSION",
    "GATE_MIN_H",
    "GATE_MIN_W",
    "MeterPipeline",
    "MeterSupervisor",
    "MeterTick",
    "optics_report",
]
