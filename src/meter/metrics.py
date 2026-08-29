"""Per-stage meter metrics for the ops health panel."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MeterMetrics:
    frames: int = 0
    optics_fail: int = 0
    fills_final: int = 0
    flagged: int = 0
    rejected_reads: int = 0
    conf_sum: float = 0.0
    conf_n: int = 0
    extras: dict[str, int] = field(default_factory=dict)

    def note_frame(self, *, optics_pass: bool, conf: float, flagged: bool) -> None:
        self.frames += 1
        if not optics_pass:
            self.optics_fail += 1
        if flagged:
            self.flagged += 1
        if conf > 0:
            self.conf_sum += conf
            self.conf_n += 1

    def note_final(self) -> None:
        self.fills_final += 1

    def note_reject(self) -> None:
        self.rejected_reads += 1

    def snapshot(self) -> dict[str, float | int]:
        return {
            "frames": self.frames,
            "optics_fail": self.optics_fail,
            "fills_final": self.fills_final,
            "flagged": self.flagged,
            "rejected_reads": self.rejected_reads,
            "flag_rate": round(self.flagged / self.frames, 4) if self.frames else 0.0,
            "mean_confidence": round(self.conf_sum / self.conf_n, 4) if self.conf_n else 0.0,
        }
