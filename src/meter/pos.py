"""POS / IFSF adapter. No feed is connected today — this is the hook."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


@dataclass
class PosTicket:
    pump_id: str
    ts: datetime
    litres: float | None = None
    amount: float | None = None
    rate: float | None = None
    ticket_id: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class PosAdapter(Protocol):
    def poll(self, pump_id: str) -> PosTicket | None: ...


class NullPosAdapter:
    """Always empty. POS remains source of truth *when it appears*."""

    def poll(self, pump_id: str) -> PosTicket | None:
        return None
