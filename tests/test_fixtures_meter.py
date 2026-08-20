"""End-to-end offline meter read from the committed synthetic clips.

Proves the whole read path (decode a real mp4 frame → crop the per-pump ROI →
seven-seg decode → litres×rate self-check) runs headless, day and night, with no
camera. The clips are synthetic (see scripts/make_fixtures.py) so this validates
the *pipeline*, not on-site accuracy.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.ocr.meter import arithmetic_check
from src.ocr.seven_seg import SevenSegConfig, SevenSegReader

cv2 = pytest.importorskip("cv2")

FIXTURES = Path(__file__).parent / "fixtures"


def _read_final_meter(clip: Path) -> tuple[dict, dict]:
    meta = json.loads(clip.with_suffix(".json").read_text())
    cap = cv2.VideoCapture(str(clip))
    try:
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(n * 0.95))  # after the sale settles
        ok, frame = cap.read()
        assert ok, f"could not read frame from {clip}"
    finally:
        cap.release()

    out: dict[str, str] = {}
    for name, (x, y, w, h) in meta["meter_rois"].items():
        roi = frame[y : y + h, x : x + w]
        reader = SevenSegReader(
            SevenSegConfig(num_digits=meta["field_digits"][name], decimals=meta["decimals"])
        )
        out[name] = reader.read(roi)[0]
    return out, meta["ground_truth"]


@pytest.mark.parametrize("clip_name", ["pump_A_day.mp4", "pump_A_night.mp4"])
def test_meter_reads_match_ground_truth(clip_name: str) -> None:
    clip = FIXTURES / clip_name
    if not clip.exists():
        pytest.skip(f"{clip_name} not generated; run scripts.make_fixtures")

    reads, gt = _read_final_meter(clip)
    assert float(reads["amount"]) == pytest.approx(gt["amount"], abs=0.01)
    assert float(reads["litres"]) == pytest.approx(gt["litres"], abs=0.01)
    assert float(reads["rate"]) == pytest.approx(gt["rate"], abs=0.01)
    # The litres x rate self-check that flags misreads must pass on a correct read.
    assert arithmetic_check(reads["litres"], reads["amount"], reads["rate"]) is True
