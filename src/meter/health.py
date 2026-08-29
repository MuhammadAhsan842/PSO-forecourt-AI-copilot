"""Pipeline health flags — ROI lost, drift, glare, low light. Fail loud, never silent."""

from __future__ import annotations

from typing import Any


def health_flags(
    optics: dict[str, Any],
    *,
    dx: float = 0.0,
    dy: float = 0.0,
    response: float = 1.0,
) -> list[str]:
    flags: list[str] = []
    w = int(optics.get("roi_width") or 0)
    h = int(optics.get("roi_height") or 0)
    if w < 8 or h < 8:
        flags.append("roi_lost")
    if not optics.get("pass_px"):
        flags.append("optics_fail")
    glare = optics.get("glare") or {}
    contrast = float(optics.get("contrast") or 1.0)
    # White 7-seg background is not glare. Washed-out (high highlight + low contrast) is.
    if float(glare.get("highlight_frac") or 0) >= 0.22 and contrast < 0.28:
        flags.append("glare")
    if float(glare.get("mean") or 128) <= 28:
        flags.append("low_light")
    if abs(float(dx)) > 12 or abs(float(dy)) > 12:
        flags.append("camera_moved")
    if float(response) < 0.15:
        flags.append("roi_lost")
    # unique, stable order
    seen: set[str] = set()
    out: list[str] = []
    for f in flags:
        if f not in seen:
            seen.add(f)
            out.append(f)
    return out
