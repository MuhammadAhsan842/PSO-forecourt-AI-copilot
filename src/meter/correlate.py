"""Camera-observed fill ↔ POS ticket ↔ vehicle visit."""

from __future__ import annotations

from datetime import datetime

from src.link.associator import Sale, SaleAssociator, VehicleVisit
from src.meter.pos import PosTicket


def provenance_for(
    *,
    camera_litres: float | None,
    camera_amount: float | None,
    camera_rate: float | None,
    pos: PosTicket | None,
    tolerance: float = 0.02,
) -> str:
    if pos is None or (pos.litres is None and pos.amount is None):
        return "camera-observed"
    litres_ok = (
        camera_litres is not None
        and pos.litres is not None
        and abs(camera_litres - pos.litres) <= max(0.05, tolerance * max(pos.litres, 1.0))
    )
    amount_ok = (
        camera_amount is not None
        and pos.amount is not None
        and abs(camera_amount - pos.amount) <= max(1.0, tolerance * max(pos.amount, 1.0))
    )
    if litres_ok or amount_ok:
        return "pos-confirmed"
    return "camera-observed"


def attach_sale(
    associator: SaleAssociator,
    *,
    pump_id: str,
    litres: float,
    amount: float,
    rate: float,
    ts: datetime,
) -> VehicleVisit | None:
    return associator.sale_recorded(
        Sale(pump_id=pump_id, amount=amount, litres=litres, rate=rate, ts=ts)
    )


def assess_fill(
    *,
    vehicle_present: bool | None,
    pos: PosTicket | None,
    t0: float | None,
    t_final: float | None,
    duration_s: float | None,
    max_lpm: float | None,
    unit_price_implied: float | None,
    price_min: float | None = None,
    price_max: float | None = None,
) -> list[tuple[str, str]]:
    """Honest discrepancy flags. Unknown vehicle/POS is not a silent match."""
    flags: list[tuple[str, str]] = []
    dispensed = None
    if t_final is not None and t0 is not None:
        dispensed = t_final - t0
    if vehicle_present is False and dispensed is not None and dispensed > 0.05:
        flags.append(("no_vehicle", "fill with no vehicle in bay"))
    if vehicle_present is True and pos is None and dispensed is not None and dispensed > 0.05:
        flags.append(("possible_unbilled", "vehicle+fill with no POS ticket"))
    if (
        pos is not None
        and dispensed is not None
        and pos.litres is not None
        and abs(dispensed - pos.litres) > max(0.15, 0.03 * max(pos.litres, 1.0))
    ):
        flags.append(("pos_mismatch", "camera amount vs POS litres disagree"))
    if (
        unit_price_implied is not None
        and price_min is not None
        and price_max is not None
        and not (price_min <= unit_price_implied <= price_max)
    ):
        flags.append(("unit_price_oob", "implied unit price outside configured band"))
    if (
        max_lpm is not None
        and dispensed is not None
        and duration_s is not None
        and duration_s > 0
        and dispensed > 0
    ):
        expected = dispensed / (max_lpm / 60.0)
        if duration_s * 2.0 < expected:
            flags.append(("duration_inconsistent", "fill faster than configured max L/min"))
    return flags
