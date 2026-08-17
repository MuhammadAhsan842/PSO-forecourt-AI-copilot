"""Number-plate reading with temporal voting.

Same shape as the meter reader: real digit/char model is fine-tuned on Pakistani
plates in Milestone 10; here we ship the plumbing — cropping, temporal vote,
format-regex validation — that we can test now.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

import numpy as np


class PlateModel(Protocol):
    """A model that returns (plate_string, confidence, bbox_in_frame_or_None)."""

    def read(self, frame: np.ndarray) -> tuple[str, float]:
        ...


class NotReadyPlateModel:
    def read(self, frame: np.ndarray) -> tuple[str, float]:
        return ("", 0.0)


@dataclass
class PlateReading:
    ts: datetime
    plate: str
    confidence: float
    format_ok: bool


def format_ok(plate: str, patterns: Iterable[str]) -> bool:
    for pat in patterns:
        try:
            if re.match(pat, plate):
                return True
        except re.error:
            continue
    return False


def temporal_vote(reads: list[PlateReading]) -> PlateReading | None:
    reads = [r for r in reads if r.plate]
    if not reads:
        return None
    weighted: Counter[str] = Counter()
    for r in reads:
        weighted[r.plate] += r.confidence
    plate, weight = weighted.most_common(1)[0]
    total = sum(weighted.values()) or 1.0
    return PlateReading(
        ts=reads[-1].ts,
        plate=plate,
        confidence=float(weight / total),
        format_ok=any(r.format_ok for r in reads if r.plate == plate),
    )


@dataclass
class PlateReader:
    model: PlateModel = field(default_factory=NotReadyPlateModel)
    min_confidence: float = 0.6
    patterns: list[str] = field(default_factory=list)
    _history: list[PlateReading] = field(default_factory=list)

    def read_frame(self, frame: np.ndarray, ts: datetime) -> PlateReading:
        plate, conf = self.model.read(frame)
        reading = PlateReading(
            ts=ts,
            plate=plate,
            confidence=conf,
            format_ok=format_ok(plate, self.patterns),
        )
        self._history.append(reading)
        if len(self._history) > 32:
            self._history = self._history[-32:]
        return reading

    def vote(self) -> PlateReading | None:
        return temporal_vote(self._history[-16:])
