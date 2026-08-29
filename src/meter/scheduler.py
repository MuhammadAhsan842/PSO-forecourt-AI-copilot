"""PTZ round-robin across enabled PTZ pumps. No-op when every pump is fixed."""

from __future__ import annotations

from src.meter.config import PumpConfig
from src.meter.ptz_goto import PtzGotoError, goto_preset


class PtzScheduler:
    def __init__(self, pumps: list[PumpConfig], *, dwell_s: float = 8.0):
        self.pumps = [p for p in pumps if p.enabled and p.is_ptz]
        self.dwell_s = dwell_s
        self._i = 0

    def next_pump(self) -> PumpConfig | None:
        if not self.pumps:
            return None
        p = self.pumps[self._i % len(self.pumps)]
        self._i += 1
        return p

    def slew(
        self,
        pump: PumpConfig,
        *,
        host: str,
        user: str,
        password: str,
    ) -> str:
        if pump.preset_index is None and not pump.preset_name:
            raise PtzGotoError(f"pump {pump.id} has no preset")
        return goto_preset(
            host=host,
            user=user,
            password=password,
            channel=pump.nvr_channel,
            preset_index=pump.preset_index,
            preset_name=pump.preset_name,
        )
