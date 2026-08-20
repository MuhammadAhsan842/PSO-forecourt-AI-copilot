"""The real seven-segment decoder must read back what the renderer drew.

This proves M9's baseline reader genuinely *measures* digits — the round-trip is
the honest substitute for "trust me, the model works" until on-site frames exist.
"""

from __future__ import annotations

import numpy as np

from src.ocr.meter import build_seven_seg_reader
from src.ocr.seven_seg import SevenSegConfig, SevenSegReader, render_seven_seg


def _read(text: str, decimals: int = 0) -> tuple[str, float]:
    img = render_seven_seg(text)
    reader = SevenSegReader(SevenSegConfig(num_digits=len(text.replace(".", "")), decimals=decimals))
    return reader.read(img)


def test_reads_every_single_digit() -> None:
    # Each digit read in a two-digit "8d" context (fixed-ROI path). A lone digit
    # cropped to its own ink loses cell width — real meters use fixed ROIs.
    for d in "0123456789":
        got, conf = _read("8" + d)
        assert got == "8" + d, f"expected 8{d}, got {got}"
        assert conf > 0.8


def test_reads_multi_digit_amount() -> None:
    got, conf = _read("50000", decimals=2)
    assert got == "500.00"
    assert conf > 0.8


def test_blank_display_returns_empty_not_zero() -> None:
    blank = np.full((72, 200, 3), 18, dtype=np.uint8)  # dark, no lit segments
    got, conf = SevenSegReader(SevenSegConfig(num_digits=3)).read(blank)
    assert got == ""
    assert conf == 0.0


def test_auto_segmentation_without_num_digits() -> None:
    img = render_seven_seg("1234")
    got, _ = SevenSegReader(SevenSegConfig(decimals=0)).read(img)
    assert got == "1234"


def test_meter_reader_end_to_end_with_arithmetic_check() -> None:
    """litres=2.00 amount=500.00 rate=250.00 → arithmetic must validate."""
    reader = build_seven_seg_reader(
        litres_digits=3, litres_decimals=2,
        amount_digits=5, amount_decimals=2,
        rate_digits=5, rate_decimals=2,
    )
    reading = reader.read_frame(
        litres_roi=render_seven_seg("200"),
        amount_roi=render_seven_seg("50000"),
        rate_roi=render_seven_seg("25000"),
        ts=__import__("datetime").datetime(2026, 8, 20, 12, 0, 0),
    )
    assert reading.litres == "2.00"
    assert reading.amount == "500.00"
    assert reading.rate == "250.00"
    assert reading.arithmetic_ok is True
