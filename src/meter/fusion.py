"""Multi-frame fusion: vote static cells only. Never fuse rolling cells."""

from __future__ import annotations

from collections import Counter

import numpy as np

from src.meter.change_rate import ROLLING


def fuse_cells(
    window: list[list[tuple[str, float, str]]],
) -> list[tuple[str, float]]:
    """``window[t][i] = (label, conf, change_label)``.

    Rolling / transitioning / blank observations are dropped for that cell.
    If a cell has *only* rolling observations in the window, return ("", 0).
    """
    if not window:
        return []
    n = len(window[0])
    out: list[tuple[str, float]] = []
    for i in range(n):
        last = window[-1]
        if i < len(last) and last[i][2] == ROLLING:
            out.append(("", 0.0))
            continue
        votes: Counter[str] = Counter()
        weight: dict[str, float] = {}
        for frame in window:
            if i >= len(frame):
                continue
            lab, conf, change = frame[i]
            if change == ROLLING or lab in {"", "blank", "transitioning", "?"}:
                continue
            votes[lab] += conf
            weight[lab] = weight.get(lab, 0.0) + conf
        if not votes:
            out.append(("", 0.0))
            continue
        winner, w = max(weight.items(), key=lambda kv: kv[1])
        total = sum(weight.values()) or 1.0
        out.append((winner, float(w / total)))
    return out


def join_digits(cells: list[tuple[str, float]], decimals: int) -> tuple[str, float]:
    if not cells or any(not c[0] for c in cells):
        return ("", 0.0)
    text = "".join(c[0] for c in cells)
    conf = float(sum(c[1] for c in cells) / len(cells))
    if decimals > 0 and len(text) > decimals:
        text = f"{text[:-decimals]}.{text[-decimals:]}"
    return text, conf


def average_static_cells(
    history: list[list[np.ndarray]],
    changes: list[str],
) -> list[np.ndarray | None]:
    """Mean of registered static cells. Rolling cells are None (estimator owns them)."""
    if not history:
        return []
    n = len(history[-1])
    out: list[np.ndarray | None] = []
    for i in range(n):
        if i < len(changes) and changes[i] == ROLLING:
            out.append(None)
            continue
        stack = [fr[i].astype(np.float32) for fr in history if i < len(fr) and fr[i].size]
        if not stack:
            out.append(None)
            continue
        out.append(np.mean(np.stack(stack, axis=0), axis=0).astype(np.uint8))
    return out
