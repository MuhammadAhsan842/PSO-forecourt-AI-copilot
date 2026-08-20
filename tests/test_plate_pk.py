"""Pakistani-plate normalisation, validation, and format-aware temporal voting."""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np

from src.ocr.plate import PlateReader
from src.ocr.plate_pk import is_valid_pk_plate, normalize_plate


def test_normalize_strips_separators_and_uppercases() -> None:
    assert normalize_plate("lea-1234") == "LEA1234"
    assert normalize_plate("ABC 123") == "ABC123"


def test_position_aware_ocr_repairs() -> None:
    # O in the digit block -> 0 ; 1 in the letter block -> I
    assert normalize_plate("LEO-12O4") == "LEO1204"
    assert normalize_plate("1EA-1234") == "IEA1234"


def test_valid_and_invalid_pk_plates() -> None:
    assert is_valid_pk_plate("LEA1234")
    assert is_valid_pk_plate("ABC123")
    assert not is_valid_pk_plate("XXXXXXXX")
    assert not is_valid_pk_plate("")


class _CannedPlateModel:
    def __init__(self, reads):
        self._reads = list(reads)

    def read(self, frame):
        return self._reads.pop(0) if self._reads else ("", 0.0)


def test_format_valid_read_outweighs_recurring_noise() -> None:
    reader = PlateReader(
        model=_CannedPlateModel(
            [("lea-1234", 0.85), ("zzzz", 0.4), ("zzzz", 0.4)]
        )
    )
    ts = datetime(2026, 8, 20, 12, 0, 0)
    for i in range(3):
        reader.read_frame(np.zeros((10, 30, 3), dtype=np.uint8), ts + timedelta(seconds=i))
    voted = reader.vote()
    assert voted is not None
    assert voted.plate == "LEA1234"
    assert voted.format_ok is True
