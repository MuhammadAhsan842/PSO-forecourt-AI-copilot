"""Phases 1–7 meter pipeline — synthetic, no camera."""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np

from src.common.types import EventKind
from src.link.associator import SaleAssociator
from src.meter.calibrate import temperature_scale
from src.meter.change_rate import ROLLING, STATIC, ChangeRateLabeler
from src.meter.config import FieldLayout, PumpConfig, Rect
from src.meter.correlate import attach_sale, provenance_for
from src.meter.estimator import LitresKalman
from src.meter.fusion import fuse_cells
from src.meter.lifecycle import FillLifecycle, FillPhase
from src.meter.ocr_cnn import TemplateDigitCnn
from src.meter.pipeline import PROVENANCE_BLOCKED, MeterPipeline
from src.meter.pos import NullPosAdapter, PosTicket
from src.meter.scheduler import PtzScheduler
from src.ocr.seven_seg import render_seven_seg


def _pump(*, gate_bezel: bool = False, settle: float = 0.5) -> PumpConfig:
    img = render_seven_seg("0000", cell_w=70, cell_h=120)
    h, w = img.shape[:2]
    bezel = Rect(x=0, y=0, w=220, h=110) if gate_bezel else Rect(x=0, y=0, w=w, h=h)
    return PumpConfig(
        id="m1",
        camera_id="pump_a",
        nvr_channel=9,
        bezel=bezel,
        fields={"litres": FieldLayout(digits=4, decimals=2)},
        settle_seconds=settle,
    )


def test_optics_gate_blocks_estimator() -> None:
    pipe = MeterPipeline(_pump(gate_bezel=True), enforce_optics_gate=True)
    frame = render_seven_seg("1000", cell_w=70, cell_h=120)
    tick = pipe.process_frame(frame, datetime(2026, 8, 28, 12, 0, 0))
    assert tick.optics_pass is False
    assert tick.litres_est is None
    assert tick.provenance == PROVENANCE_BLOCKED
    assert tick.needs_review is True
    assert any(e.kind == EventKind.METER_OPTICS_FAIL for e in tick.events)


def test_fusion_skips_rolling_cells() -> None:
    window = [
        [("1", 0.9, STATIC), ("2", 0.9, ROLLING)],
        [("1", 0.8, STATIC), ("3", 0.9, ROLLING)],
        [("1", 0.7, STATIC), ("4", 0.9, ROLLING)],
    ]
    fused = fuse_cells(window)
    assert fused[0][0] == "1"
    assert fused[1] == ("", 0.0)


def test_change_rate_labels_a_big_mae_as_rolling() -> None:
    lab = ChangeRateLabeler(roll_mae=5.0, blank_mean=5.0)
    a = np.full((20, 12), 80, dtype=np.uint8)
    b = np.full((20, 12), 200, dtype=np.uint8)
    assert lab.label([a]) == [STATIC]
    assert lab.label([b]) == [ROLLING]


def test_kalman_rejects_mid_fill_drop() -> None:
    kf = LitresKalman()
    t0 = kf.update(1.0, 0.2, meas_conf=0.9)
    t1 = kf.update(2.0, 0.2, meas_conf=0.9)
    t2 = kf.update(0.5, 0.2, meas_conf=0.9)
    assert t1.litres > t0.litres
    assert t2.litres >= t1.litres - 0.05


def test_temperature_scale_t_gt_1_reduces_confidence() -> None:
    assert temperature_scale(0.95, 1.8) < 0.95


def test_cnn_reads_synthetic_eight() -> None:
    img = render_seven_seg("8", cell_w=40, cell_h=72)
    lab, conf = TemplateDigitCnn().classify_cell(img)
    assert lab == "8"
    assert conf > 0.4


def test_synthetic_fill_emits_start_t0_stop_final() -> None:
    pipe = MeterPipeline(_pump(settle=0.5), enforce_optics_gate=False)
    values = ["0000", "0125", "0250", "0500", "0750", "1000", "1000", "1000", "1000"]
    ts = datetime(2026, 8, 28, 12, 0, 0)
    kinds: list[EventKind] = []
    last = None
    for i, raw in enumerate(values):
        frame = render_seven_seg(raw, cell_w=70, cell_h=120)
        last = pipe.process_frame(frame, ts + timedelta(seconds=i * 0.4))
        kinds.extend(e.kind for e in last.events)
    assert EventKind.METER_FILL_START in kinds
    assert EventKind.METER_FILL_T0 in kinds
    assert EventKind.METER_FILL_STOP in kinds
    assert EventKind.METER_FILL_FINAL in kinds
    assert last is not None
    assert last.provenance == "camera-observed"
    assert last.litres_est is not None
    assert last.fill_phase == FillPhase.FINAL.value
    assert last.t0 is not None and last.t_final is not None
    assert last.t0 == 0.0
    assert last.t_final == 10.0
    assert last.amount == 10.0
    final = next(e for e in reversed(last.events) if e.kind == EventKind.METER_FILL_FINAL)
    assert final.payload["schema_version"] == 2
    assert final.payload["amount"] == last.amount
    assert final.payload["billed"] is False


def test_vehicle_present_without_pos_is_unbilled() -> None:
    pipe = MeterPipeline(_pump(settle=0.5), enforce_optics_gate=False, vehicle_present=True)
    values = ["0000", "0125", "0250", "0500", "0750", "1000", "1000", "1000", "1000"]
    ts = datetime(2026, 8, 28, 12, 0, 0)
    kinds: list[EventKind] = []
    last = None
    for i, raw in enumerate(values):
        frame = render_seven_seg(raw, cell_w=70, cell_h=120)
        last = pipe.process_frame(frame, ts + timedelta(seconds=i * 0.4))
        kinds.extend(e.kind for e in last.events)
    assert EventKind.METER_UNBILLED in kinds
    assert last is not None and last.needs_review is True
    assert EventKind.METER_NEEDS_REVIEW in kinds


def test_lifecycle_reset_on_near_zero() -> None:
    life = FillLifecycle(settle_seconds=0.4, start_litres=0.08)
    ts = datetime(2026, 8, 28, 12, 0, 0)
    life.step(ts=ts, litres=1.0, rate_lps=0.1, optics_ok=True, conf=0.9)
    life.step(ts=ts + timedelta(seconds=1), litres=2.0, rate_lps=0.1, optics_ok=True, conf=0.9)
    ev = life.step(ts=ts + timedelta(seconds=2), litres=0.0, rate_lps=0.0, optics_ok=True, conf=0.9)
    assert any(e.phase == FillPhase.RESET for e in ev)
    assert life.phase == FillPhase.IDLE


def test_null_pos_stays_camera_observed() -> None:
    assert NullPosAdapter().poll("m1") is None
    assert (
        provenance_for(camera_litres=10.0, camera_amount=None, camera_rate=None, pos=None)
        == "camera-observed"
    )


def test_pos_match_is_confirmed() -> None:
    pos = PosTicket(pump_id="m1", ts=datetime(2026, 8, 28, 12, 0, 0), litres=10.0, amount=2500.0)
    assert (
        provenance_for(camera_litres=10.05, camera_amount=2500.0, camera_rate=250.0, pos=pos)
        == "pos-confirmed"
    )


def test_correlate_attaches_sale_to_vehicle() -> None:
    assoc = SaleAssociator()
    ts = datetime(2026, 8, 28, 12, 0, 0)
    assoc.vehicle_arrived(track_id=7, pump_id="m1", ts=ts)
    visit = attach_sale(assoc, pump_id="m1", litres=10.0, amount=2500.0, rate=250.0, ts=ts)
    assert visit is not None and visit.track_id == 7


def test_ptz_scheduler_skips_fixed_cams() -> None:
    fixed = _pump()
    ptz = _pump()
    ptz.id = "m1_ptz"
    ptz.is_ptz = True
    ptz.preset_index = 2
    sch = PtzScheduler([fixed, ptz])
    assert sch.next_pump() is not None
    assert sch.next_pump().id == "m1_ptz"


def test_average_static_cells_skips_rolling() -> None:
    from src.meter.change_rate import ROLLING
    from src.meter.fusion import average_static_cells

    a = np.full((4, 4, 3), 10, dtype=np.uint8)
    b = np.full((4, 4, 3), 20, dtype=np.uint8)
    out = average_static_cells([[a, a], [b, b]], ["static", ROLLING])
    assert out[0] is not None
    assert int(out[0].mean()) == 15
    assert out[1] is None


def test_carry_replaces_transitioning_from_prediction() -> None:
    from src.meter.carry import apply_transition_and_carry, predicted_digits

    pred = predicted_digits(10.00, num_digits=4, decimals=2)
    assert pred == ["1", "0", "0", "0"]
    out, flags = apply_transition_and_carry(
        ["1", "0", "transitioning", "0"], predicted=pred
    )
    assert out[2] == "0"
    assert "transition_predicted" in flags


def test_anomaly_unbilled_and_no_vehicle() -> None:
    from src.meter.correlate import assess_fill

    nv = assess_fill(
        vehicle_present=False,
        pos=None,
        t0=1.0,
        t_final=10.0,
        duration_s=20.0,
        max_lpm=None,
        unit_price_implied=None,
    )
    assert any(a[0] == "no_vehicle" for a in nv)
    ub = assess_fill(
        vehicle_present=True,
        pos=None,
        t0=1.0,
        t_final=10.0,
        duration_s=20.0,
        max_lpm=None,
        unit_price_implied=None,
    )
    assert any(a[0] == "possible_unbilled" for a in ub)


def test_health_flags_glare() -> None:
    from src.meter.health import health_flags

    flags = health_flags(
        {
            "pass_px": True,
            "roi_width": 640,
            "roi_height": 320,
            "contrast": 0.1,
            "glare": {"highlight_frac": 0.4, "mean": 200},
        },
        dx=0,
        dy=0,
        response=1.0,
    )
    assert "glare" in flags
    clean = health_flags(
        {
            "pass_px": True,
            "roi_width": 640,
            "roi_height": 320,
            "contrast": 0.8,
            "glare": {"highlight_frac": 0.4, "mean": 200},
        },
        dx=0,
        dy=0,
        response=1.0,
    )
    assert "glare" not in clean


def test_synth_blur_still_reads_eight() -> None:
    from src.meter.ocr_cnn import TemplateDigitCnn
    from src.meter.synth import augment_digit
    from src.ocr.seven_seg import render_seven_seg

    img = augment_digit(render_seven_seg("8", cell_w=40, cell_h=72), blur=1.0, brightness=0.9)
    lab, conf = TemplateDigitCnn().classify_cell(img)
    assert lab == "8"
    assert conf > 0.3
