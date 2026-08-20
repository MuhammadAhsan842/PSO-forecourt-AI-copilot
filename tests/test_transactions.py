"""Sale↔vehicle linking + drive-off with amount (Milestone 10 acceptance)."""

from __future__ import annotations

from datetime import datetime, timedelta

from src.common.types import EventKind
from src.events.engine import ListSink
from src.link.transactions import TransactionCoordinator

T0 = datetime(2026, 8, 20, 12, 0, 0)


def _coord() -> tuple[TransactionCoordinator, ListSink]:
    sink = ListSink()
    return TransactionCoordinator(sink, camera_id="ptz1", drive_off_grace_seconds=20), sink


def test_normal_sale_links_to_vehicle_and_emits_sale_recorded() -> None:
    coord, sink = _coord()
    coord.vehicle_settled(track_id=7, pump_id="A", ts=T0)
    coord.meter_sale(pump_id="A", amount=500.0, litres=2.0, rate=250.0, ts=T0 + timedelta(seconds=30))
    # Pays and leaves after a normal dwell → no drive-off.
    coord.vehicle_departed(track_id=7, pump_id="A", ts=T0 + timedelta(seconds=90), plate="LEA1234")

    kinds = [e.kind for e in sink.events]
    assert EventKind.SALE_RECORDED in kinds
    assert EventKind.DRIVE_OFF not in kinds
    sale = next(e for e in sink.events if e.kind == EventKind.SALE_RECORDED)
    assert sale.payload["amount"] == 500.0
    assert sale.track_id == 7


def test_drive_off_fires_with_unpaid_amount() -> None:
    coord, sink = _coord()
    coord.vehicle_settled(track_id=9, pump_id="B", ts=T0)
    coord.meter_sale(pump_id="B", amount=1500.0, litres=6.0, rate=250.0, ts=T0 + timedelta(seconds=40))
    # Leaves 5s after the meter settled — too soon to have paid.
    coord.vehicle_departed(track_id=9, pump_id="B", ts=T0 + timedelta(seconds=45), plate="ABC123")

    drive_offs = [e for e in sink.events if e.kind == EventKind.DRIVE_OFF]
    assert len(drive_offs) == 1
    assert drive_offs[0].payload["unpaid_amount"] == 1500.0
    assert drive_offs[0].payload["plate"] == "ABC123"


def test_sale_with_no_vehicle_present_is_not_attributed() -> None:
    coord, sink = _coord()
    # Meter dispenses but no vehicle track in the bay.
    visit = coord.meter_sale(pump_id="C", amount=300.0, litres=1.2, rate=250.0, ts=T0)
    assert visit is None
    assert sink.events == []
