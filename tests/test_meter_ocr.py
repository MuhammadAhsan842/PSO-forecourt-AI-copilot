"""Milestone 9 acceptance: the pieces we can test without a trained model.

Digit majority-vote, arithmetic check, and the sale state machine.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np

from src.ocr.meter import (
    MeterReader,
    MeterSaleState,
    arithmetic_check,
    majority_vote_digits,
)


class _CannedClassifier:
    """Returns pre-programmed reads in order."""

    def __init__(self, reads):
        self._reads = list(reads)

    def read(self, roi):
        if not self._reads:
            return ("", 0.0)
        return self._reads.pop(0)


def _blank():
    return np.zeros((32, 96), dtype=np.uint8)


def test_majority_vote_picks_the_stable_digit() -> None:
    reads = [("123", 0.9), ("123", 0.95), ("124", 0.4), ("133", 0.3)]
    winner, conf = majority_vote_digits(reads)
    assert winner == "123"
    assert 0 < conf <= 1


def test_arithmetic_check_within_tolerance() -> None:
    assert arithmetic_check("2.00", "500.00", "250.00", tolerance=0.02) is True
    assert arithmetic_check("2.00", "600.00", "250.00", tolerance=0.02) is False
    assert arithmetic_check("bad", "500", "250") is None


def test_meter_state_machine_transitions() -> None:
    reader = MeterReader(
        classifier_litres=_CannedClassifier([]),
        classifier_amount=_CannedClassifier(
            [("0.00", 0.9), ("120.00", 0.9), ("360.00", 0.9), ("500.00", 0.9), ("500.00", 0.9), ("500.00", 0.9)]
        ),
        classifier_rate=_CannedClassifier([]),
        settle_seconds=1.0,
    )
    ts = datetime(2026, 8, 17, 12, 0, 0)
    for step in range(6):
        reader.read_frame(
            litres_roi=_blank(),
            amount_roi=_blank(),
            rate_roi=_blank(),
            ts=ts + timedelta(seconds=step),
        )
    assert reader.state == MeterSaleState.SETTLED
