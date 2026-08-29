"""Confidence calibration — temperature scaling on [0, 1] scores."""

from __future__ import annotations

import math


def temperature_scale(conf: float, temperature: float = 1.4) -> float:
    """T > 1 pulls over-confident scores down. T = 1 is identity."""
    c = min(max(float(conf), 1e-6), 1.0 - 1e-6)
    t = max(float(temperature), 1e-3)
    logit = math.log(c / (1.0 - c))
    return 1.0 / (1.0 + math.exp(-logit / t))


def scale_field(text: str, conf: float, temperature: float = 1.4) -> tuple[str, float]:
    if not text or "?" in text:
        return text, min(conf, 0.35)
    return text, round(temperature_scale(conf, temperature), 4)
