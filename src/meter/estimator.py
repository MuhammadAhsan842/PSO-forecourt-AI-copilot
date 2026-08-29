"""Monotonic litres estimator. State ``x = [T, r]`` (volume, L/s).

``max_lpm`` comes from pump config. ``None`` means the site has not confirmed a
physical ceiling — we only forbid negative flow, we do not invent a PSO L/min.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class EstimatorState:
    litres: float
    rate_lps: float
    litres_var: float
    rate_var: float


class LitresKalman:
    def __init__(
        self,
        *,
        max_lpm: float | None = None,
        q_t: float = 0.02,
        q_r: float = 0.8,
        r_meas: float = 0.4,
    ):
        self.max_lpm = max_lpm
        self.q_t = q_t
        self.q_r = q_r
        self.r_meas = r_meas
        self.x = np.array([0.0, 0.0], dtype=np.float64)
        self.P = np.diag([4.0, 1.0])
        self._inited = False
        self._last_z: float | None = None
        self.rejected = 0

    def reset(self) -> None:
        self.x[:] = 0.0
        self.P = np.diag([4.0, 1.0])
        self._inited = False
        self._last_z = None
        self.rejected = 0

    def predict(self, dt: float) -> EstimatorState:
        dt = max(0.0, float(dt))
        f = np.array([[1.0, dt], [0.0, 1.0]])
        q = np.diag([self.q_t * dt, self.q_r * dt])
        self.x = f @ self.x
        self.P = f @ self.P @ f.T + q
        self._clamp()
        return self.state()

    def update(self, z: float | None, dt: float, *, meas_conf: float = 1.0) -> EstimatorState:
        self.predict(dt)
        if z is None or meas_conf <= 0.05:
            return self.state()
        if not self._inited:
            self.x[0] = float(z)
            self._inited = True
            self._last_z = float(z)
            self._clamp()
            return self.state()
        # Reject an OCR blip that runs volume backwards vs the last accepted z.
        if (
            self._last_z is not None
            and float(z) + 0.2 < self._last_z
            and self._last_z > 0.3
            and float(z) > 0.15
        ):
            self.rejected += 1
            return self.state()
        self._last_z = float(z)
        if abs(float(z) - self.x[0]) < 0.08:
            self.x[1] *= 0.25
        h = np.array([[1.0, 0.0]])
        r = self.r_meas / max(meas_conf, 0.05)
        y = float(z) - float((h @ self.x)[0])
        s = float((h @ self.P @ h.T)[0, 0] + r)
        k = (self.P @ h.T) / s
        self.x = self.x + (k.ravel() * y)
        self.P = (np.eye(2) - k @ h) @ self.P
        self._clamp()
        return self.state()

    def _clamp(self) -> None:
        self.x[0] = max(0.0, float(self.x[0]))
        self.x[1] = max(0.0, float(self.x[1]))
        if self.max_lpm is not None:
            self.x[1] = min(self.x[1], float(self.max_lpm) / 60.0)

    @property
    def inited(self) -> bool:
        return self._inited

    def predicted_litres(self) -> float | None:
        if not self._inited:
            return None
        return float(self.x[0])

    def reading_confidence(self) -> float:
        """Map litres covariance to [0, 1]. High variance → low confidence."""
        return float(1.0 / (1.0 + max(0.0, self.P[0, 0])))

    def state(self) -> EstimatorState:
        return EstimatorState(
            litres=float(self.x[0]),
            rate_lps=float(self.x[1]),
            litres_var=float(self.P[0, 0]),
            rate_var=float(self.P[1, 1]),
        )
