"""Fuel-dispenser meter reading.

Two clean pieces:

  1. ``DigitClassifier`` — a swappable interface. The real implementation is a
     small YOLO/CNN fine-tuned on THIS dispenser's 7-seg font (Milestone 9). For
     M0–M8, we ship a stub that says "not-ready" so nothing lies about the digits.

  2. Pure logic that we CAN test now:
     - ``majority_vote_digits`` — combine N per-frame reads into one stable value.
     - ``arithmetic_check`` — verify |amount − litres × rate| < tolerance.
     - ``MeterReader.step`` — the sale state machine (reset → count-up → settle → reset).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Protocol

import numpy as np

from src.common.logging import get_logger

log = get_logger(__name__)


class DigitClassifier(Protocol):
    """Read digits from an already-cropped ROI (single field, e.g. Litres)."""

    def read(self, roi: np.ndarray) -> tuple[str, float]:  # (digits, confidence)
        ...


class NotReadyClassifier:
    """Placeholder. Returns empty string with zero confidence."""

    def read(self, roi: np.ndarray) -> tuple[str, float]:
        return ("", 0.0)


class MeterSaleState(str, Enum):
    IDLE = "idle"
    COUNTING = "counting"
    SETTLED = "settled"
    RESET = "reset"


@dataclass
class MeterReading:
    ts: datetime
    litres: str
    amount: str
    rate: str
    litres_conf: float
    amount_conf: float
    rate_conf: float
    arithmetic_ok: bool | None = None


def majority_vote_digits(reads: list[tuple[str, float]]) -> tuple[str, float]:
    """Per-position majority vote weighted by confidence.

    ``reads`` = list of (digits_string, confidence). Strings can differ in length;
    we align by right-padding with spaces (decimals fixed by ROI layout).
    """
    reads = [r for r in reads if r[0]]
    if not reads:
        return ("", 0.0)
    max_len = max(len(r[0]) for r in reads)
    padded = [(r[0].rjust(max_len), r[1]) for r in reads]

    result_chars: list[str] = []
    confs: list[float] = []
    for pos in range(max_len):
        weights: Counter[str] = Counter()
        for digits, conf in padded:
            ch = digits[pos]
            weights[ch] += conf
        winner, weight = max(weights.items(), key=lambda kv: kv[1])
        total = sum(weights.values()) or 1.0
        result_chars.append(winner)
        confs.append(weight / total)
    return ("".join(result_chars).lstrip(), float(np.mean(confs)))


def arithmetic_check(
    litres: str, amount: str, rate: str, tolerance: float = 0.02
) -> bool | None:
    """Return True/False when we can compute the check, None when we can't parse."""
    try:
        litres_v = float(litres)
        amount_v = float(amount)
        rate_v = float(rate)
    except ValueError:
        return None
    if amount_v == 0 or rate_v == 0:
        return None
    expected = litres_v * rate_v
    err = abs(expected - amount_v) / amount_v
    return err <= tolerance


@dataclass
class MeterReader:
    """State machine that tracks a single dispenser through one sale."""

    classifier_litres: DigitClassifier = field(default_factory=NotReadyClassifier)
    classifier_amount: DigitClassifier = field(default_factory=NotReadyClassifier)
    classifier_rate: DigitClassifier = field(default_factory=NotReadyClassifier)

    reset_epsilon: float = 0.02
    settle_seconds: float = 2.0
    arithmetic_tolerance: float = 0.02

    state: MeterSaleState = MeterSaleState.IDLE
    _last_reads: list[MeterReading] = field(default_factory=list)
    _last_change_ts: datetime | None = None
    _last_amount_num: float | None = None

    def read_frame(
        self,
        *,
        litres_roi: np.ndarray,
        amount_roi: np.ndarray,
        rate_roi: np.ndarray,
        ts: datetime,
    ) -> MeterReading:
        litres, lc = self.classifier_litres.read(litres_roi)
        amount, ac = self.classifier_amount.read(amount_roi)
        rate, rc = self.classifier_rate.read(rate_roi)
        reading = MeterReading(
            ts=ts,
            litres=litres,
            amount=amount,
            rate=rate,
            litres_conf=lc,
            amount_conf=ac,
            rate_conf=rc,
        )
        reading.arithmetic_ok = arithmetic_check(
            litres, amount, rate, tolerance=self.arithmetic_tolerance
        )
        self._last_reads.append(reading)
        if len(self._last_reads) > 32:
            self._last_reads = self._last_reads[-32:]
        self._advance_state(reading)
        return reading

    def _advance_state(self, reading: MeterReading) -> None:
        amt = _to_float(reading.amount)
        if amt is None:
            return

        if self._last_amount_num is None:
            self._last_amount_num = amt
            self._last_change_ts = reading.ts
            return

        delta = amt - self._last_amount_num

        if amt <= self.reset_epsilon and self._last_amount_num > self.reset_epsilon * 5:
            self.state = MeterSaleState.RESET
        elif delta > 0.01:
            self.state = MeterSaleState.COUNTING
            self._last_change_ts = reading.ts
        elif (
            abs(delta) < 0.01
            and self.state == MeterSaleState.COUNTING
            and self._last_change_ts is not None
            and (reading.ts - self._last_change_ts).total_seconds() >= self.settle_seconds
        ):
            self.state = MeterSaleState.SETTLED

        self._last_amount_num = amt

    def vote(self) -> MeterReading | None:
        """Combine recent reads into one voted reading. Called at SETTLED."""
        if not self._last_reads:
            return None
        recent = self._last_reads[-16:]
        litres, lc = majority_vote_digits([(x.litres, x.litres_conf) for x in recent])
        amount, ac = majority_vote_digits([(x.amount, x.amount_conf) for x in recent])
        rate, rc = majority_vote_digits([(x.rate, x.rate_conf) for x in recent])
        return MeterReading(
            ts=recent[-1].ts,
            litres=litres,
            amount=amount,
            rate=rate,
            litres_conf=lc,
            amount_conf=ac,
            rate_conf=rc,
            arithmetic_ok=arithmetic_check(
                litres, amount, rate, tolerance=self.arithmetic_tolerance
            ),
        )


def _to_float(s: str) -> float | None:
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def build_seven_seg_reader(
    *,
    litres_digits: int | None = None,
    litres_decimals: int = 2,
    amount_digits: int | None = None,
    amount_decimals: int = 2,
    rate_digits: int | None = None,
    rate_decimals: int = 2,
    settle_seconds: float = 2.0,
    arithmetic_tolerance: float = 0.02,
) -> MeterReader:
    """Construct a ``MeterReader`` backed by the real classical seven-seg decoder.

    This is the M9 baseline reader — it returns measured digits from a clean
    display. ``*_digits`` / ``*_decimals`` are the per-pump ROI layout from config
    (the "fixed per pump" split the plan calls for). Swap in a CNN classifier
    later without touching callers.
    """
    from src.ocr.seven_seg import SevenSegConfig, SevenSegReader

    return MeterReader(
        classifier_litres=SevenSegReader(
            SevenSegConfig(num_digits=litres_digits, decimals=litres_decimals)
        ),
        classifier_amount=SevenSegReader(
            SevenSegConfig(num_digits=amount_digits, decimals=amount_decimals)
        ),
        classifier_rate=SevenSegReader(
            SevenSegConfig(num_digits=rate_digits, decimals=rate_decimals)
        ),
        settle_seconds=settle_seconds,
        arithmetic_tolerance=arithmetic_tolerance,
    )
