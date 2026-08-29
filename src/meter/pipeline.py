"""Per-frame meter pipeline. Camera-observed numbers; optics FAIL blocks the estimator."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

import numpy as np

from src.common.types import EventKind, EventRecord
from src.meter.calibrate import scale_field
from src.meter.carry import apply_transition_and_carry, predicted_digits
from src.meter.change_rate import ChangeRateLabeler
from src.meter.config import FieldLayout, PumpConfig, Rect
from src.meter.contract import FILL_SCHEMA_VERSION, fill_contract
from src.meter.correlate import assess_fill, provenance_for
from src.meter.estimator import LitresKalman
from src.meter.fusion import fuse_cells, join_digits
from src.meter.health import health_flags
from src.meter.lifecycle import FillLifecycle, FillPhase, LifecycleEvent
from src.meter.metrics import MeterMetrics
from src.meter.ocr_cnn import CnnFieldReader, TemplateDigitCnn
from src.meter.optics import crop_roi, optics_report
from src.meter.pos import NullPosAdapter, PosAdapter
from src.meter.register import register_roi
from src.meter.segment import split_cells
from src.ocr.meter import MeterSaleState, arithmetic_check
from src.ocr.seven_seg import SevenSegConfig, SevenSegReader

PROVENANCE_BLOCKED = "optics-blocked"
PROVENANCE_CAMERA = "camera-observed"
PROVENANCE_POS = "pos-confirmed"

_FLAG_KIND = {
    "no_vehicle": EventKind.METER_NO_VEHICLE,
    "possible_unbilled": EventKind.METER_UNBILLED,
    "pos_mismatch": EventKind.METER_POS_MISMATCH,
}

# Informational carry flags do not force human review.
_REVIEW_FLAGS = {
    "roi_lost",
    "glare",
    "low_light",
    "camera_moved",
    "optics_fail",
    "impossible_read",
    "no_vehicle",
    "possible_unbilled",
    "pos_mismatch",
    "unit_price_oob",
    "duration_inconsistent",
}


def _tier(conf: float, *, needs_review: bool) -> str:
    if needs_review or conf < 0.5:
        return "review"
    if conf < 0.85:
        return "medium"
    return "high"


def _to_float(s: str) -> float | None:
    try:
        v = float(s)
    except (TypeError, ValueError):
        return None
    if "?" in str(s):
        return None
    return v


def _crop_field(frame: np.ndarray, bezel: Rect, layout: FieldLayout | None) -> np.ndarray:
    r = layout.roi if layout is not None and layout.roi is not None else bezel
    return crop_roi(frame, r.x, r.y, r.w, r.h)


@dataclass
class MeterTick:
    ts: datetime
    pump_id: str
    camera_id: str
    optics: dict = field(default_factory=dict)
    optics_pass: bool = False
    litres_raw: str = ""
    amount_raw: str = ""
    rate_raw: str = ""
    litres_est: float | None = None
    rate_lps: float | None = None
    confidence: float = 0.0
    confidence_tier: str = "review"
    provenance: str = PROVENANCE_BLOCKED
    needs_review: bool = True
    source: str = "blocked"
    state: str = MeterSaleState.IDLE.value
    fill_phase: str = FillPhase.IDLE.value
    flags: list[str] = field(default_factory=list)
    t0: float | None = None
    t_final: float | None = None
    amount: float | None = None
    events: list[EventRecord] = field(default_factory=list)
    bezel_frame: np.ndarray | None = field(default=None, repr=False)


class MeterPipeline:
    def __init__(
        self,
        pump: PumpConfig,
        *,
        enforce_optics_gate: bool = True,
        pos: PosAdapter | None = None,
        temperature: float = 1.4,
        vehicle_present: bool | None = None,
    ):
        self.pump = pump
        self.enforce_optics_gate = enforce_optics_gate
        self.pos = pos or NullPosAdapter()
        self.temperature = temperature
        self.vehicle_present = vehicle_present
        self.cnn = TemplateDigitCnn()
        litres = pump.fields.get("litres") or FieldLayout()
        amount = pump.fields.get("amount")
        rate = pump.fields.get("rate")
        self._ssocr_l = SevenSegReader(
            SevenSegConfig(num_digits=litres.digits, decimals=litres.decimals)
        )
        self._cnn_l = CnnFieldReader(
            num_digits=litres.digits, decimals=litres.decimals, cnn=self.cnn
        )
        self._ssocr_a = (
            SevenSegReader(SevenSegConfig(num_digits=amount.digits, decimals=amount.decimals))
            if amount
            else None
        )
        self._ssocr_r = (
            SevenSegReader(SevenSegConfig(num_digits=rate.digits, decimals=rate.decimals))
            if rate
            else None
        )
        self._change = ChangeRateLabeler()
        self._estimator = LitresKalman(max_lpm=pump.max_lpm)
        self._life = FillLifecycle(settle_seconds=pump.settle_seconds)
        self._fuse_win: deque[list[tuple[str, float, str]]] = deque(maxlen=8)
        self._template: np.ndarray | None = None
        self._last_ts: datetime | None = None
        self._optics_fail_emitted = False
        self._health_emitted: set[str] = set()
        self.metrics = MeterMetrics()

    def process_frame(self, frame: np.ndarray, ts: datetime) -> MeterTick:
        bezel = crop_roi(frame, *self.pump.bezel.as_tuple())
        aligned, dx, dy, resp = register_roi(bezel, self._template)
        if self._template is None:
            self._template = aligned.copy()
        optics = optics_report(aligned)
        optics["register_dx"] = round(dx, 2)
        optics["register_dy"] = round(dy, 2)
        optics["register_response"] = round(resp, 4)
        gate_ok = bool(optics["pass_px"]) or not self.enforce_optics_gate
        flags = health_flags(optics, dx=dx, dy=dy, response=resp)
        if not self.enforce_optics_gate:
            flags = [f for f in flags if f != "optics_fail"]

        tick = MeterTick(
            ts=ts,
            pump_id=self.pump.id,
            camera_id=self.pump.camera_id,
            optics=optics,
            optics_pass=bool(optics["pass_px"]),
            bezel_frame=aligned,
            flags=list(flags),
        )

        litres_layout = self.pump.fields.get("litres") or FieldLayout()
        litres_roi = (
            aligned
            if litres_layout.roi is None
            else _crop_field(frame, self.pump.bezel, litres_layout)
        )

        raw_s, conf_s = self._ssocr_l.read(litres_roi)
        raw_c, conf_c = self._cnn_l.read(litres_roi)
        if conf_c > conf_s:
            litres_raw, litres_conf, source = raw_c, conf_c, "cnn"
        else:
            litres_raw, litres_conf, source = raw_s, conf_s, "ssocr"
        litres_raw, litres_conf = scale_field(litres_raw, litres_conf, self.temperature)

        cells = split_cells(litres_roi, litres_layout.digits)
        changes = self._change.label(cells) if cells else []
        cell_obs: list[tuple[str, float, str]] = []
        labels = []
        for i, cell in enumerate(cells):
            lab, c = self.cnn.classify_cell(cell)
            ch = changes[i] if i < len(changes) else "static"
            cell_obs.append((lab, c, ch))
            labels.append(lab)
        pred = None
        litres_hat = self._estimator.predicted_litres()
        if litres_hat is not None:
            pred = predicted_digits(
                litres_hat,
                num_digits=litres_layout.digits,
                decimals=litres_layout.decimals,
            )
        labels, carry_flags = apply_transition_and_carry(labels, predicted=pred)
        flags.extend(carry_flags)
        for i, lab in enumerate(labels):
            if i < len(cell_obs):
                _, c, ch = cell_obs[i]
                cell_obs[i] = (lab, c, ch)
        self._fuse_win.append(cell_obs)
        fused = fuse_cells(list(self._fuse_win))
        fused_text, fused_conf = join_digits(fused, litres_layout.decimals)
        if fused_text and fused_conf >= litres_conf and (not litres_raw or fused_text == litres_raw):
            litres_raw, litres_conf, source = fused_text, fused_conf, "fused"

        amount_raw = rate_raw = ""
        amount_layout = self.pump.fields.get("amount")
        rate_layout = self.pump.fields.get("rate")
        if self._ssocr_a and amount_layout and amount_layout.roi is not None:
            amount_raw, _ = self._ssocr_a.read(_crop_field(frame, self.pump.bezel, amount_layout))
        if self._ssocr_r and rate_layout and rate_layout.roi is not None:
            rate_raw, _ = self._ssocr_r.read(_crop_field(frame, self.pump.bezel, rate_layout))

        tick.litres_raw = litres_raw
        tick.amount_raw = amount_raw
        tick.rate_raw = rate_raw

        dt = 0.2
        if self._last_ts is not None:
            dt = max(0.01, (ts - self._last_ts).total_seconds())
        self._last_ts = ts

        z = _to_float(litres_raw) if gate_ok else None
        prev_rej = self._estimator.rejected
        est = self._estimator.update(z, dt, meas_conf=litres_conf if gate_ok else 0.0)
        if self._estimator.rejected > prev_rej:
            self.metrics.note_reject()
            flags.append("impossible_read")

        est_conf = self._estimator.reading_confidence()
        arith = arithmetic_check(litres_raw, amount_raw, rate_raw)
        needs = (not gate_ok) or litres_conf < 0.5 or arith is False or ("?" in litres_raw)
        pos = self.pos.poll(self.pump.id)
        prov = (
            PROVENANCE_BLOCKED
            if not gate_ok
            else provenance_for(
                camera_litres=est.litres if gate_ok else None,
                camera_amount=_to_float(amount_raw),
                camera_rate=_to_float(rate_raw),
                pos=pos,
            )
        )
        if not gate_ok:
            tick.litres_est = None
            tick.rate_lps = None
            tick.confidence = 0.0
            tick.source = "blocked"
        else:
            tick.litres_est = round(est.litres, 3)
            tick.rate_lps = round(est.rate_lps, 4)
            tick.confidence = round(float(min(litres_conf, est_conf if est_conf else litres_conf)), 4)
            tick.source = source
        tick.provenance = prov
        tick.needs_review = (
            needs
            or prov == PROVENANCE_BLOCKED
            or any(f in _REVIEW_FLAGS for f in flags)
        )
        tick.confidence_tier = _tier(tick.confidence, needs_review=tick.needs_review)
        tick.flags = list(dict.fromkeys(flags))

        life_events = self._life.step(
            ts=ts,
            litres=z if gate_ok else None,
            rate_lps=est.rate_lps if gate_ok else 0.0,
            optics_ok=gate_ok,
            conf=tick.confidence,
        )
        tick.state = self._life.sale_state.value
        tick.fill_phase = self._life.phase.value
        tick.t0 = self._life.t0_litres
        tick.t_final = self._life.t_final
        if tick.t0 is not None and tick.t_final is not None:
            tick.amount = round(tick.t_final - tick.t0, 3)

        will_final = any(ev.phase == FillPhase.FINAL for ev in life_events)
        if will_final:
            self.metrics.note_final()
            dur = None
            if self._life.fill_start_ts is not None:
                dur = (ts - self._life.fill_start_ts).total_seconds()
            price = None
            amt_v = _to_float(amount_raw)
            if amt_v and tick.amount:
                price = amt_v / tick.amount
            for flag, detail in assess_fill(
                vehicle_present=self.vehicle_present,
                pos=pos,
                t0=tick.t0,
                t_final=tick.t_final,
                duration_s=dur,
                max_lpm=self.pump.max_lpm,
                unit_price_implied=price,
            ):
                flags.append(flag)
                tick.flags.append(flag)
                kind = _FLAG_KIND.get(flag, EventKind.METER_HEALTH)
                tick.events.append(
                    self._event(kind, tick, tick.confidence, {"anomaly": detail, "health_flag": flag})
                )
            tick.flags = list(dict.fromkeys(tick.flags))
            if any(f in _REVIEW_FLAGS for f in tick.flags):
                tick.needs_review = True
                tick.confidence_tier = _tier(tick.confidence, needs_review=True)

        tick.events = self._to_records(life_events, tick) + tick.events
        if not gate_ok and not self._optics_fail_emitted:
            tick.events.append(
                self._event(
                    EventKind.METER_OPTICS_FAIL, tick, 0.0, {"gate_reason": optics["gate_reason"]}
                )
            )
            self._optics_fail_emitted = True
        for hf in tick.flags:
            if hf in {"glare", "low_light", "camera_moved", "roi_lost"} and hf not in self._health_emitted:
                tick.events.append(
                    self._event(EventKind.METER_HEALTH, tick, tick.confidence, {"health_flag": hf})
                )
                self._health_emitted.add(hf)
        if will_final and tick.needs_review:
            tick.events.append(self._event(EventKind.METER_NEEDS_REVIEW, tick, tick.confidence, {}))
        self.metrics.note_frame(
            optics_pass=tick.optics_pass, conf=tick.confidence, flagged=tick.needs_review
        )
        return tick

    def _to_records(self, events: list[LifecycleEvent], tick: MeterTick) -> list[EventRecord]:
        kind_map = {
            FillPhase.START: EventKind.METER_FILL_START,
            FillPhase.T0: EventKind.METER_FILL_T0,
            FillPhase.STOP: EventKind.METER_FILL_STOP,
            FillPhase.FINAL: EventKind.METER_FILL_FINAL,
        }
        out: list[EventRecord] = []
        for ev in events:
            kind = kind_map.get(ev.phase)
            if kind is None:
                continue
            extra = {k: ("" if v is None else v) for k, v in ev.extra.items()}
            extra["phase"] = ev.phase.value
            if kind == EventKind.METER_FILL_FINAL:
                extra.update(
                    fill_contract(
                        pump_id=tick.pump_id,
                        camera_id=tick.camera_id,
                        fill_start_ts=self._life.fill_start_ts,
                        fill_end_ts=tick.ts,
                        t0=tick.t0,
                        t_final=tick.t_final,
                        litres=tick.litres_est,
                        amount=tick.amount,
                        per_reading_confidence=tick.confidence,
                        final_total_confidence=tick.confidence,
                        flags=tick.flags,
                        provenance=tick.provenance,
                    )
                )
            out.append(self._event(kind, tick, ev.confidence, extra))
        return out

    def _event(
        self,
        kind: EventKind,
        tick: MeterTick,
        confidence: float,
        extra: dict,
    ) -> EventRecord:
        payload: dict[str, str | int | float | bool | None] = {
            "schema_version": FILL_SCHEMA_VERSION,
            "pump_id": tick.pump_id,
            "provenance": tick.provenance,
            "optics_pass": tick.optics_pass,
            "source": tick.source,
            "confidence_tier": tick.confidence_tier,
            "needs_review": tick.needs_review,
            "litres_raw": tick.litres_raw or None,
            "litres_est": tick.litres_est,
            "rate_lps": tick.rate_lps,
            "fill_phase": tick.fill_phase,
            "flags": ",".join(tick.flags),
            "billed": False,
        }
        payload.update(extra)
        return EventRecord(
            id=str(uuid4()),
            kind=kind,
            camera_id=tick.camera_id,
            zone_id=tick.pump_id,
            confidence=confidence,
            ts=tick.ts,
            payload=payload,
        )
