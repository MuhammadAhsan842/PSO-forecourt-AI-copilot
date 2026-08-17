"""Sale ↔ vehicle association (Milestone 10).

Idea: while a vehicle sits in a pump_bay we track it (from M5/M6). When the
meter reader emits a settled sale on that pump, we associate the settled sale
with the vehicle track that is currently in the bay. On the vehicle's departure
we attach the plate read.

If the vehicle leaves before we register a sale, we have a "drive-off with
amount" candidate — the last known settled amount at that pump.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class Sale:
    pump_id: str
    amount: float
    litres: float
    rate: float
    ts: datetime


@dataclass
class VehicleVisit:
    track_id: int
    pump_id: str
    arrived_at: datetime
    departed_at: datetime | None = None
    plate: str | None = None
    sale: Sale | None = None
    drive_off: bool = False


class SaleAssociator:
    """One instance per site. Deterministic + tested in isolation."""

    def __init__(self, *, grace_seconds: float = 8.0):
        self.grace = timedelta(seconds=grace_seconds)
        self._active: dict[tuple[str, int], VehicleVisit] = {}  # (pump_id, track_id)
        self._closed: list[VehicleVisit] = []

    def vehicle_arrived(self, *, track_id: int, pump_id: str, ts: datetime) -> None:
        key = (pump_id, track_id)
        if key in self._active:
            return
        self._active[key] = VehicleVisit(
            track_id=track_id, pump_id=pump_id, arrived_at=ts
        )

    def vehicle_departed(
        self, *, track_id: int, pump_id: str, ts: datetime, plate: str | None = None
    ) -> VehicleVisit | None:
        key = (pump_id, track_id)
        visit = self._active.pop(key, None)
        if visit is None:
            return None
        visit.departed_at = ts
        if plate:
            visit.plate = plate
        if visit.sale is None:
            visit.drive_off = True
        self._closed.append(visit)
        return visit

    def sale_recorded(self, sale: Sale) -> VehicleVisit | None:
        """Attach the sale to whichever vehicle is currently in that pump bay.

        Preference: the visit with the most recent ``arrived_at`` <= sale.ts.
        """
        candidates = [
            v
            for (pump, _tid), v in self._active.items()
            if pump == sale.pump_id and v.arrived_at <= sale.ts + self.grace
        ]
        if not candidates:
            return None
        best = max(candidates, key=lambda v: v.arrived_at)
        best.sale = sale
        best.drive_off = False
        return best

    def closed_visits(self) -> list[VehicleVisit]:
        return list(self._closed)
