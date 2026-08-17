"""Milestone 10 acceptance: temporal vote + Pakistani format regex."""

from __future__ import annotations

from datetime import datetime

from src.ocr.plate import PlateReading, format_ok, temporal_vote

PK_PATTERNS = [r"^[A-Z]{2,3}-?[0-9]{2,4}$", r"^[A-Z]{3}[0-9]{2,3}$"]


def test_pakistani_format() -> None:
    assert format_ok("LEA-1234", PK_PATTERNS)
    assert format_ok("LEA1234", PK_PATTERNS)
    assert not format_ok("****", PK_PATTERNS)


def test_temporal_vote_picks_best_reading() -> None:
    ts = datetime.utcnow()
    reads = [
        PlateReading(ts=ts, plate="LEA-1234", confidence=0.9, format_ok=True),
        PlateReading(ts=ts, plate="LEA-1234", confidence=0.85, format_ok=True),
        PlateReading(ts=ts, plate="LEA-1284", confidence=0.4, format_ok=True),
    ]
    result = temporal_vote(reads)
    assert result is not None
    assert result.plate == "LEA-1234"
    assert result.confidence > 0.5
