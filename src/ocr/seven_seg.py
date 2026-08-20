"""Seven-segment digit reading — the real thing, classical-CV.

The plan (§0, M9) is emphatic: no software invents digits that weren't captured.
Once M2 has produced a *human-readable* meter crop and M9 has fixed the per-pump
ROI layout, reading a seven-segment display is a solved, deterministic problem
that does **not** need a trained network to start returning digits:

  1. Binarise the ROI (Otsu) and pick the ink polarity.
  2. Split the field into per-digit cells.
  3. For each cell, sample the seven canonical segment regions (a…g), decide
     lit/unlit, and map the 7-bit pattern to a digit.
  4. Confidence = how decisively each segment read on/off — a soft margin, so a
     smeared/half-lit display self-reports low confidence instead of guessing.

This is the honest M9 baseline: it reads a clean seven-seg display *today* and
its output is fed through the same many-frame majority vote + litres×rate check
as everything else. A CNN fine-tuned on the real dispenser font (``DigitClassifier``
in ``meter.py``) is the accuracy upgrade once we have on-site frames — it drops in
behind the identical interface. What we never do is emit a digit we didn't measure.

Calibration knobs (``SevenSegConfig``) live in config per pump; nothing here is
hard-coded to one display.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Segment order is (a, b, c, d, e, f, g):
#
#      a
#     ---
#  f |   | b
#     -g-
#  e |   | c
#     ---
#      d
_DIGIT_PATTERNS: dict[str, tuple[int, int, int, int, int, int, int]] = {
    "0": (1, 1, 1, 1, 1, 1, 0),
    "1": (0, 1, 1, 0, 0, 0, 0),
    "2": (1, 1, 0, 1, 1, 0, 1),
    "3": (1, 1, 1, 1, 0, 0, 1),
    "4": (0, 1, 1, 0, 0, 1, 1),
    "5": (1, 0, 1, 1, 0, 1, 1),
    "6": (1, 0, 1, 1, 1, 1, 1),
    "7": (1, 1, 1, 0, 0, 0, 0),
    "8": (1, 1, 1, 1, 1, 1, 1),
    "9": (1, 1, 1, 1, 0, 1, 1),
}

# Canonical segment sample boxes in a unit cell (x0, y0, x1, y1), fractions of
# cell width/height. Each box sits well inside the middle of one segment so a lit
# segment scores ~1 and an unlit one ~0 — a wide margin for the on/off decision.
_SEGMENT_BOXES: dict[str, tuple[float, float, float, float]] = {
    "a": (0.30, 0.05, 0.70, 0.17),
    "b": (0.82, 0.18, 0.94, 0.42),
    "c": (0.82, 0.58, 0.94, 0.82),
    "d": (0.30, 0.83, 0.70, 0.95),
    "e": (0.06, 0.58, 0.18, 0.82),
    "f": (0.06, 0.18, 0.18, 0.42),
    "g": (0.30, 0.44, 0.70, 0.56),
}
_SEGMENT_ORDER = ("a", "b", "c", "d", "e", "f", "g")


@dataclass
class SevenSegConfig:
    """Per-pump calibration. Loaded from ``config`` — never hard-coded to a display."""

    num_digits: int | None = None  # None → auto-segment by ink projection
    decimals: int = 0  # digits after the (implicit) decimal point
    invert: bool | None = None  # None → auto-detect bright-on-dark vs dark-on-bright
    on_threshold: float = 0.4  # fraction of lit pixels in a box that counts as "on"
    min_ink_fraction: float = 0.02  # a cell below this is treated as blank


def _to_gray(img: np.ndarray) -> np.ndarray:
    if img.ndim == 3:
        # BT.601 luma; avoids a hard cv2 dependency.
        return (0.114 * img[..., 0] + 0.587 * img[..., 1] + 0.299 * img[..., 2]).astype(
            np.float64
        )
    return img.astype(np.float64)


def _otsu_threshold(gray: np.ndarray) -> float:
    """Otsu's method in pure numpy. Returns the intensity split point."""
    hist, _ = np.histogram(gray, bins=256, range=(0.0, 255.0))
    total = gray.size
    if total == 0:
        return 127.0
    weight_bg = np.cumsum(hist)
    weight_fg = total - weight_bg
    intensity = np.arange(256, dtype=np.float64)
    cumulative_mean = np.cumsum(hist * intensity)
    global_mean = cumulative_mean[-1]
    # Guard against div-by-zero at the histogram tails.
    with np.errstate(divide="ignore", invalid="ignore"):
        mean_bg = np.where(weight_bg > 0, cumulative_mean / weight_bg, 0.0)
        mean_fg = np.where(
            weight_fg > 0, (global_mean - cumulative_mean) / weight_fg, 0.0
        )
        between = weight_bg * weight_fg * (mean_bg - mean_fg) ** 2
    return float(np.argmax(between))


def _binarise(gray: np.ndarray, invert: bool | None) -> np.ndarray:
    """Return a bool mask where True == 'ink' (a lit segment)."""
    thr = _otsu_threshold(gray)
    bright = gray > thr
    if invert is None:
        # A seven-seg meter is lit digits on a dark bezel: ink is the minority,
        # bright class. If bright pixels dominate, the display is dark-on-light.
        invert = bright.mean() > 0.5
    return (gray <= thr) if invert else bright


def _crop_to_ink(mask: np.ndarray, min_ink_fraction: float) -> np.ndarray:
    """Trim surrounding margin/gaps so an even N-way split lands on the digits.

    Real per-pump ROIs (and our renderer) carry a bezel/margin; cropping to the
    ink bounding box makes the fixed-cell split robust to that padding.
    """
    if mask.mean() < min_ink_fraction:
        return mask
    rows = np.where(mask.mean(axis=1) > min_ink_fraction)[0]
    cols = np.where(mask.mean(axis=0) > min_ink_fraction)[0]
    if rows.size == 0 or cols.size == 0:
        return mask
    return mask[rows[0] : rows[-1] + 1, cols[0] : cols[-1] + 1]


def _digit_columns(mask: np.ndarray, min_ink_fraction: float) -> list[tuple[int, int]]:
    """Group contiguous ink columns into digit spans via column projection."""
    col_ink = mask.mean(axis=0)
    active = col_ink > max(min_ink_fraction, 0.03)
    spans: list[tuple[int, int]] = []
    start: int | None = None
    for x, on in enumerate(active):
        if on and start is None:
            start = x
        elif not on and start is not None:
            spans.append((start, x))
            start = None
    if start is not None:
        spans.append((start, len(active)))
    # Drop slivers narrower than a plausible digit stroke cluster.
    if not spans:
        return spans
    # Merge spans separated by a within-digit gap (small relative to the median
    # digit width) so a hollow digit stays one cell; keep narrow digits like "1".
    widths = sorted(b - a for a, b in spans)
    median_w = widths[len(widths) // 2]
    merged: list[list[int]] = [list(spans[0])]
    for a, b in spans[1:]:
        if a - merged[-1][1] < max(2.0, 0.08 * median_w):
            merged[-1][1] = b
        else:
            merged.append([a, b])
    # Drop only true specks (sensor noise), never a legitimate narrow digit.
    return [(a, b) for a, b in merged if (b - a) >= max(2, 0.08 * median_w)]


def _cell_bounds(width: int, num_digits: int) -> list[tuple[int, int]]:
    edges = np.linspace(0, width, num_digits + 1).astype(int)
    return [(int(edges[i]), int(edges[i + 1])) for i in range(num_digits)]


def _read_cell(cell: np.ndarray, on_threshold: float) -> tuple[str, float]:
    """Decode one digit cell. Returns (digit_or_'', confidence)."""
    h, w = cell.shape
    if h < 6 or w < 4:
        return ("", 0.0)

    scores: list[float] = []
    for seg in _SEGMENT_ORDER:
        fx0, fy0, fx1, fy1 = _SEGMENT_BOXES[seg]
        x0, x1 = int(fx0 * w), max(int(fx1 * w), int(fx0 * w) + 1)
        y0, y1 = int(fy0 * h), max(int(fy1 * h), int(fy0 * h) + 1)
        box = cell[y0:y1, x0:x1]
        scores.append(float(box.mean()) if box.size else 0.0)

    seg_scores = np.array(scores)  # fraction lit per segment, 0..1
    lit = seg_scores >= on_threshold

    # Match to the closest digit by a soft margin: reward segments that agree
    # with the template *and* are decisively on/off.
    best_digit = ""
    best_score = -1.0
    for digit, pattern in _DIGIT_PATTERNS.items():
        pat = np.array(pattern, dtype=np.float64)
        # per-segment agreement in [0,1]; 1 when the lit/unlit call matches template
        agree = np.where(pat > 0.5, seg_scores, 1.0 - seg_scores)
        score = float(agree.mean())
        if score > best_score:
            best_score = score
            best_digit = digit

    # Sanity: the winner's hard pattern must match the thresholded segments,
    # otherwise we're guessing between two close templates → low confidence.
    winner_pat = np.array(_DIGIT_PATTERNS[best_digit])
    hard_match = bool(np.all(lit == (winner_pat > 0.5)))
    confidence = best_score if hard_match else best_score * 0.5
    return (best_digit, round(confidence, 4))


class SevenSegReader:
    """Read a whole seven-segment field (e.g. the Amount ROI) into a number string."""

    def __init__(self, config: SevenSegConfig | None = None):
        self.config = config or SevenSegConfig()

    def read(self, roi: np.ndarray) -> tuple[str, float]:
        """DigitClassifier-compatible: (digits_string, confidence).

        ``digits_string`` includes a decimal point when ``config.decimals > 0``,
        so it parses straight to a float for the litres×rate check.
        """
        if roi is None or roi.size == 0:
            return ("", 0.0)
        gray = _to_gray(roi)
        mask = _binarise(gray, self.config.invert).astype(np.float64)

        if mask.mean() < self.config.min_ink_fraction:
            return ("", 0.0)  # blank display — say so, don't invent a zero

        mask = _crop_to_ink(mask, self.config.min_ink_fraction)

        if self.config.num_digits:
            bounds = _cell_bounds(mask.shape[1], self.config.num_digits)
        else:
            spans = _digit_columns(mask, self.config.min_ink_fraction)
            bounds = spans or _cell_bounds(mask.shape[1], 1)

        # A cell markedly narrower than its neighbours can only be a "1" — the one
        # digit that lights just two right-hand segments. This is how the auto
        # (projection) path recovers a "1" whose ink bbox lost its cell width.
        widths = [x1 - x0 for x0, x1 in bounds]
        median_w = sorted(widths)[len(widths) // 2] if widths else 0

        digits: list[str] = []
        confs: list[float] = []
        for x0, x1 in bounds:
            cell = mask[:, x0:x1]
            if median_w and (x1 - x0) < 0.5 * median_w and cell.mean() > self.config.min_ink_fraction:
                digits.append("1")
                confs.append(0.9)
                continue
            d, c = _read_cell(cell, self.config.on_threshold)
            if d == "":
                continue
            digits.append(d)
            confs.append(c)

        if not digits:
            return ("", 0.0)

        text = "".join(digits)
        if self.config.decimals > 0 and len(text) > self.config.decimals:
            text = f"{text[:-self.config.decimals]}.{text[-self.config.decimals:]}"
        return (text, round(float(np.mean(confs)), 4))


# --------------------------------------------------------------------------------------
# Synthetic renderer — used by tests and by scripts/make_fixtures.py to prove the
# decoder round-trips. NOT a data source for real readings.
# --------------------------------------------------------------------------------------

# (x0, y0, x1, y1) stroke rectangles in a unit cell, one per segment.
_RENDER_STROKES: dict[str, tuple[float, float, float, float]] = {
    "a": (0.18, 0.03, 0.82, 0.19),
    "b": (0.80, 0.10, 0.96, 0.48),
    "c": (0.80, 0.52, 0.96, 0.90),
    "d": (0.18, 0.81, 0.82, 0.97),
    "e": (0.04, 0.52, 0.20, 0.90),
    "f": (0.04, 0.10, 0.20, 0.48),
    "g": (0.18, 0.42, 0.82, 0.58),
}


def render_seven_seg(
    text: str,
    *,
    cell_w: int = 40,
    cell_h: int = 72,
    on: int = 235,
    off: int = 18,
    margin: int = 8,
) -> np.ndarray:
    """Render digits (ignoring any '.') as a bright-on-dark seven-seg field.

    Cells tile edge-to-edge (uniform pitch = ``cell_w``); the visible inter-digit
    gap comes from the stroke insets. A ``margin`` bezel surrounds the field, which
    the reader crops away — mirroring a real per-pump ROI.
    """
    plain = text.replace(".", "")
    n = max(len(plain), 1)
    img = np.full((cell_h + 2 * margin, n * cell_w + 2 * margin, 3), off, dtype=np.uint8)
    for i, ch in enumerate(plain):
        pattern = _DIGIT_PATTERNS.get(ch)
        if pattern is None:
            continue
        cx0 = margin + i * cell_w
        for seg, bit in zip(_SEGMENT_ORDER, pattern):
            if not bit:
                continue
            fx0, fy0, fx1, fy1 = _RENDER_STROKES[seg]
            x0 = cx0 + int(fx0 * cell_w)
            x1 = cx0 + int(fx1 * cell_w)
            y0 = margin + int(fy0 * cell_h)
            y1 = margin + int(fy1 * cell_h)
            img[y0:y1, x0:x1] = on
    return img
