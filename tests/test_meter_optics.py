"""Phase 0 optics gate — synthetic, no camera."""

from __future__ import annotations

import numpy as np

from src.meter.optics import GATE_MIN_H, GATE_MIN_W, crop_roi, optics_report
from src.meter.ptz_goto import dahua_goto_preset_url, parse_dahua_presets
from src.ocr.seven_seg import render_seven_seg


def test_cli_help_exits_zero() -> None:
    from scripts.meter_optics_proof import main

    try:
        main(["--help"])
    except SystemExit as exc:
        assert exc.code == 0
    else:
        raise AssertionError("argparse --help should SystemExit")


def test_crop_roi_clamps_to_frame() -> None:
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    roi = crop_roi(frame, -10, -5, 1000, 1000)
    assert roi.shape == (100, 200, 3)


def test_pixel_gate_fails_on_known_ch9_idle_crop() -> None:
    roi = np.zeros((110, 220, 3), dtype=np.uint8)
    report = optics_report(roi)
    assert report["roi_width"] == 220
    assert report["roi_height"] == 110
    assert report["pass_px"] is False
    assert "FAIL pixel gate" in report["gate_reason"]
    assert report["gate_min_wh"] == [GATE_MIN_W, GATE_MIN_H]


def test_pixel_gate_passes_at_600x300() -> None:
    roi = np.zeros((GATE_MIN_H, GATE_MIN_W, 3), dtype=np.uint8)
    report = optics_report(roi)
    assert report["pass_px"] is True
    assert report["gate_reason"] == "PASS pixel gate"


def test_pixel_gate_fails_if_only_one_axis_meets_min() -> None:
    wide = np.zeros((100, 800, 3), dtype=np.uint8)
    tall = np.zeros((400, 200, 3), dtype=np.uint8)
    assert optics_report(wide)["pass_px"] is False
    assert optics_report(tall)["pass_px"] is False


def test_glare_and_contrast_on_flat_vs_high_swing() -> None:
    flat = np.full((320, 640, 3), 128, dtype=np.uint8)
    hot = np.full((320, 640, 3), 255, dtype=np.uint8)
    checker = np.zeros((320, 640, 3), dtype=np.uint8)
    checker[:, 320:] = 255
    flat_r = optics_report(flat)
    hot_r = optics_report(hot)
    chk_r = optics_report(checker)
    assert flat_r["contrast"] < 0.05
    assert hot_r["glare"]["highlight_frac"] > 0.9
    assert chk_r["contrast"] > 0.9


def test_display_guess_is_coarse_not_a_classifier() -> None:
    img = render_seven_seg("8888", cell_w=80, cell_h=140)
    guess = optics_report(img)["display_guess"]
    assert guess in {"seven_segment", "mechanical_wheel", "graphic_lcd", "unknown"}


def test_display_guess_graphic_lcd_blue_field() -> None:
    roi = np.zeros((200, 400, 3), dtype=np.uint8)
    roi[:, :, 0] = 180  # BGR: strong blue, low texture
    assert optics_report(roi)["display_guess"] == "graphic_lcd"


def test_dahua_goto_preset_url_matches_on_site_form() -> None:
    url = dahua_goto_preset_url("192.168.1.114", 80, 10, 2)
    assert url == (
        "http://192.168.1.114:80/cgi-bin/ptz.cgi"
        "?action=start&channel=10&code=GotoPreset&arg1=0&arg2=2&arg3=0"
    )


def test_parse_dahua_presets() -> None:
    body = (
        "presets[0].Index=1\n"
        "presets[0].Name=3hree machine\n"
        "presets[1].Index=2\n"
        "presets[1].Name=overview\n"
    )
    rows = parse_dahua_presets(body)
    assert len(rows) == 2
    assert rows[0]["Index"] == "1"
    assert rows[1]["Name"] == "overview"
