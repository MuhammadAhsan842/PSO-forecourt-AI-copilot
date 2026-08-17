"""Milestone 10 — sale↔vehicle link + drive-off detection."""

from __future__ import annotations

from datetime import datetime, timedelta

from src.link.associator import Sale, SaleAssociator


def test_sale_attributed_to_vehicle_in_bay() -> None:
    assoc = SaleAssociator()
    t0 = datetime(2026, 8, 17, 12, 0, 0)

    assoc.vehicle_arrived(track_id=7, pump_id="A", ts=t0)
    visit = assoc.sale_recorded(
        Sale(pump_id="A", amount=500.0, litres=2.0, rate=250.0, ts=t0 + timedelta(seconds=30))
    )
    assert visit is not None and visit.track_id == 7
    assert visit.sale is not None and visit.sale.amount == 500.0


def test_drive_off_when_departure_without_sale() -> None:
    assoc = SaleAssociator()
    t0 = datetime(2026, 8, 17, 12, 0, 0)

    assoc.vehicle_arrived(track_id=42, pump_id="B", ts=t0)
    visit = assoc.vehicle_departed(
        track_id=42, pump_id="B", ts=t0 + timedelta(seconds=45), plate="LEA-1234"
    )
    assert visit is not None
    assert visit.drive_off is True
    assert visit.plate == "LEA-1234"
