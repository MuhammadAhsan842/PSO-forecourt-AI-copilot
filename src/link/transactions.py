"""Transaction coordinator — the sale↔vehicle payoff (Milestone 10).

Ties three streams into the events PSO actually cares about:

  * ``vehicle_settled_at_pump`` (from the event engine, M6/M8)  → a visit opens.
  * a settled meter sale on that pump (from the meter reader, M9) → the amount is
    linked to the vehicle in the bay and a ``SALE_RECORDED`` event fires.
  * the vehicle leaving the bay (exit-line crossing or track loss)  → the visit
    closes; a departure that happens too soon after fuel was dispensed to have
    been paid for is flagged ``DRIVE_OFF`` **with the unpaid amount**.

The drive-off rule is an honest operational *proxy*: a pure-vision pilot cannot
see a card tap, so "left within ``drive_off_grace`` seconds of the meter
settling" stands in for "left without paying". It ships with a snapshot and the
one-tap true/false control, and the HITL feedback loop (§2.5) tunes the window —
exactly the kind of alert the plan says to measure and iterate on, never a silent
automated accusation.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

from src.common.logging import get_logger
from src.common.types import EventKind, EventRecord
from src.events.engine import EventSink
from src.link.associator import Sale, SaleAssociator, VehicleVisit

log = get_logger(__name__)


class TransactionCoordinator:
    """One per site. Deterministic and unit-tested in isolation."""

    def __init__(
        self,
        sink: EventSink,
        *,
        camera_id: str,
        drive_off_grace_seconds: float = 20.0,
        associate_grace_seconds: float = 8.0,
        clock: Callable[[], datetime] = datetime.utcnow,
    ):
        self.sink = sink
        self.camera_id = camera_id
        self.drive_off_grace = timedelta(seconds=drive_off_grace_seconds)
        self.assoc = SaleAssociator(grace_seconds=associate_grace_seconds)
        self.clock = clock
        self._settle_ts: dict[tuple[str, int], datetime] = {}

    # --- inputs ------------------------------------------------------------

    def vehicle_settled(self, *, track_id: int, pump_id: str, ts: datetime) -> None:
        self.assoc.vehicle_arrived(track_id=track_id, pump_id=pump_id, ts=ts)
        log.info(
            "visit_opened",
            extra={"camera_id": self.camera_id, "track_id": track_id, "context": {"pump": pump_id}},
        )

    def meter_sale(
        self, *, pump_id: str, amount: float, litres: float, rate: float, ts: datetime
    ) -> VehicleVisit | None:
        """A meter sale settled on ``pump_id``. Link it and emit SALE_RECORDED."""
        sale = Sale(pump_id=pump_id, amount=amount, litres=litres, rate=rate, ts=ts)
        visit = self.assoc.sale_recorded(sale)
        if visit is None:
            # Fuel dispensed but no vehicle currently tracked in the bay — worth a
            # note for reconciliation, but not attributable to a vehicle yet.
            log.warning(
                "sale_unlinked",
                extra={"camera_id": self.camera_id, "context": {"pump": pump_id, "amount": amount}},
            )
            return None
        self._settle_ts[(pump_id, visit.track_id)] = ts
        self._emit(
            EventKind.SALE_RECORDED,
            track_id=visit.track_id,
            payload={
                "pump_id": pump_id,
                "amount": round(amount, 2),
                "litres": round(litres, 3),
                "rate": round(rate, 3),
            },
            ts=ts,
        )
        return visit

    def vehicle_departed(
        self, *, track_id: int, pump_id: str, ts: datetime, plate: str | None = None
    ) -> VehicleVisit | None:
        """Close the visit; fire DRIVE_OFF with amount if it left unpaid-fast."""
        visit = self.assoc.vehicle_departed(track_id=track_id, pump_id=pump_id, ts=ts, plate=plate)
        if visit is None:
            return None

        if visit.sale is not None:
            settle_ts = self._settle_ts.pop((pump_id, track_id), None)
            too_soon = settle_ts is not None and (ts - settle_ts) < self.drive_off_grace
            if too_soon:
                self._emit(
                    EventKind.DRIVE_OFF,
                    track_id=track_id,
                    payload={
                        "pump_id": pump_id,
                        "unpaid_amount": round(visit.sale.amount, 2),
                        "litres": round(visit.sale.litres, 3),
                        "plate": plate or "",
                        "seconds_after_sale": round((ts - settle_ts).total_seconds(), 1),
                    },
                    ts=ts,
                )
        return visit

    # --- helpers -----------------------------------------------------------

    def _emit(
        self,
        kind: EventKind,
        *,
        track_id: int | None,
        payload: dict,
        ts: datetime,
    ) -> None:
        record = EventRecord(
            id=f"{kind.value}-{ts.strftime('%Y%m%dT%H%M%S%f')}-{track_id or 'x'}",
            kind=kind,
            camera_id=self.camera_id,
            track_id=track_id,
            confidence=1.0,
            payload=payload,
            ts=ts,
        )
        self.sink.emit(record)
        log.info(
            "event_emitted",
            extra={
                "camera_id": self.camera_id,
                "track_id": track_id,
                "event": kind.value,
                "context": payload,
            },
        )
