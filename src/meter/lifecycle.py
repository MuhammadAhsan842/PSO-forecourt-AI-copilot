"""Fill lifecycle: idle → start → T0 → stop → T_final → reset.

Wraps ``MeterSaleState`` rather than replacing it. Emits versioned events;
does not persist them (caller / supervisor does).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from src.ocr.meter import MeterSaleState


class FillPhase(str, Enum):
    IDLE = "idle"
    START = "start"
    T0 = "t0"
    FILLING = "filling"
    STOP = "stop"
    FINAL = "final"
    RESET = "reset"


@dataclass
class LifecycleEvent:
    phase: FillPhase
    ts: datetime
    litres: float | None
    confidence: float
    extra: dict = field(default_factory=dict)


class FillLifecycle:
    def __init__(self, *, settle_seconds: float = 2.0, start_litres: float = 0.08):
        self.settle_seconds = settle_seconds
        self.start_litres = start_litres
        self.phase = FillPhase.IDLE
        self.sale_state = MeterSaleState.IDLE
        self.t0_litres: float | None = None
        self.t_final: float | None = None
        self.fill_start_ts: datetime | None = None
        self._last_t: float = 0.0
        self._have_sample: bool = False
        self._last_change: datetime | None = None
        self._stop_since: datetime | None = None

    def reset(self) -> None:
        self.phase = FillPhase.IDLE
        self.sale_state = MeterSaleState.IDLE
        self.t0_litres = None
        self.t_final = None
        self.fill_start_ts = None
        self._last_t = 0.0
        self._have_sample = False
        self._last_change = None
        self._stop_since = None

    def step(
        self,
        *,
        ts: datetime,
        litres: float | None,
        rate_lps: float,
        optics_ok: bool,
        conf: float,
    ) -> list[LifecycleEvent]:
        events: list[LifecycleEvent] = []
        if litres is None or not optics_ok:
            return events

        rising = litres > self._last_t + 0.02
        if litres <= self.start_litres * 0.5 and self.phase in {
            FillPhase.FINAL,
            FillPhase.STOP,
            FillPhase.FILLING,
            FillPhase.T0,
            FillPhase.START,
        }:
            self.phase = FillPhase.RESET
            self.sale_state = MeterSaleState.RESET
            events.append(
                LifecycleEvent(FillPhase.RESET, ts, litres, conf, {"t_final": self.t_final})
            )
            self.phase = FillPhase.IDLE
            self.sale_state = MeterSaleState.IDLE
            self.t0_litres = None
            self.t_final = None
            self.fill_start_ts = None
            self._last_t = litres
            self._have_sample = True
            self._stop_since = None
            return events

        if self.phase == FillPhase.IDLE and litres >= self.start_litres and rising:
            self.phase = FillPhase.START
            self.sale_state = MeterSaleState.COUNTING
            events.append(LifecycleEvent(FillPhase.START, ts, litres, conf, {}))
            self.phase = FillPhase.T0
            # Baseline is the last idle reading, not the first incrementing frame.
            self.t0_litres = self._last_t if self._have_sample else litres
            self.fill_start_ts = ts
            events.append(LifecycleEvent(FillPhase.T0, ts, litres, conf, {"T0": self.t0_litres}))
            self.phase = FillPhase.FILLING
            self._last_change = ts
            self._stop_since = None

        elif self.phase == FillPhase.FILLING:
            self.sale_state = MeterSaleState.COUNTING
            if litres > self._last_t + 0.05:
                self._last_change = ts
                self._stop_since = None
            else:
                if self._stop_since is None:
                    self._stop_since = ts
                held = (ts - self._stop_since).total_seconds()
                if held >= self.settle_seconds:
                    self.phase = FillPhase.STOP
                    events.append(LifecycleEvent(FillPhase.STOP, ts, litres, conf, {}))
                    self.phase = FillPhase.FINAL
                    self.t_final = litres
                    self.sale_state = MeterSaleState.SETTLED
                    amt = None
                    if self.t0_litres is not None:
                        amt = round(float(litres) - float(self.t0_litres), 3)
                    events.append(
                        LifecycleEvent(
                            FillPhase.FINAL,
                            ts,
                            litres,
                            conf,
                            {
                                "T0": self.t0_litres,
                                "T_final": litres,
                                "amount": amt,
                                "fill_start_ts": (
                                    self.fill_start_ts.isoformat() if self.fill_start_ts else None
                                ),
                                "fill_end_ts": ts.isoformat(),
                            },
                        )
                    )

        self._last_t = litres
        self._have_sample = True
        return events
