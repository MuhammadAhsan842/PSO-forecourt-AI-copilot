"""Per-cell digit classifier (0–9, blank, transitioning).

This is the CNN *slot*. A real fine-tuned network drops in behind the same
``classify_cell`` interface once ``models/meter_7seg/`` has weights. Until then
we use a template nearest-neighbour on the synthetic 7-seg renderer — same
labels, honest confidence, no invented digits.
"""

from __future__ import annotations

import numpy as np

from src.ocr.seven_seg import render_seven_seg

LABELS = ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "blank", "transitioning")
CELL_H = 36
CELL_W = 20


def _gray_u8(img: np.ndarray) -> np.ndarray:
    if img.ndim == 2:
        g = img
    else:
        g = (0.114 * img[..., 0] + 0.587 * img[..., 1] + 0.299 * img[..., 2]).astype(np.uint8)
    import cv2

    return cv2.resize(g, (CELL_W, CELL_H), interpolation=cv2.INTER_AREA)


def _vec(img: np.ndarray) -> np.ndarray:
    v = _gray_u8(img).astype(np.float32).ravel()
    n = float(np.linalg.norm(v)) + 1e-6
    return v / n


def _build_bank() -> tuple[np.ndarray, tuple[str, ...]]:
    mats: list[np.ndarray] = []
    names: list[str] = []
    for d in "0123456789":
        img = render_seven_seg(d, cell_w=CELL_W, cell_h=CELL_H, vmargin=2)
        mats.append(_vec(img))
        names.append(d)
    blank = np.full((CELL_H + 4, CELL_W, 3), 18, dtype=np.uint8)
    mats.append(_vec(blank))
    names.append("blank")
    a = render_seven_seg("8", cell_w=CELL_W, cell_h=CELL_H, vmargin=2)
    b = render_seven_seg("0", cell_w=CELL_W, cell_h=CELL_H, vmargin=2)
    trans = ((a.astype(np.float32) + b.astype(np.float32)) / 2).astype(np.uint8)
    mats.append(_vec(trans))
    names.append("transitioning")
    return np.stack(mats, axis=0), tuple(names)


class TemplateDigitCnn:
    """Nearest-neighbour stand-in for a 12-class 7-seg CNN."""

    def __init__(self) -> None:
        self.bank, self.names = _build_bank()

    def classify_cell(self, cell: np.ndarray) -> tuple[str, float]:
        if cell is None or cell.size == 0 or min(cell.shape[:2]) < 4:
            return ("blank", 0.0)
        v = _vec(cell)
        sims = self.bank @ v
        idx = int(np.argmax(sims))
        best = float(sims[idx])
        runner = float(np.partition(sims, -2)[-2]) if sims.size > 1 else 0.0
        margin = max(0.0, best - runner)
        conf = float(np.clip(0.5 * (best + 1.0) * (0.5 + 0.5 * margin), 0.0, 1.0))
        ink = float(_gray_u8(cell).mean())
        if ink < 22:
            return ("blank", round(max(conf, 0.7), 4))
        label = self.names[idx]
        if label == "transitioning" or (best < 0.55 and 22 <= ink <= 200):
            return ("transitioning", round(min(conf, 0.45), 4))
        return (label, round(conf, 4))


class CnnFieldReader:
    """DigitClassifier-compatible field reader using per-cell CNN labels."""

    def __init__(self, *, num_digits: int, decimals: int, cnn: TemplateDigitCnn | None = None):
        self.num_digits = num_digits
        self.decimals = decimals
        self.cnn = cnn or TemplateDigitCnn()

    def read(self, roi: np.ndarray) -> tuple[str, float]:
        from src.meter.segment import split_cells

        cells = split_cells(roi, self.num_digits)
        if not cells:
            return ("", 0.0)
        digits: list[str] = []
        confs: list[float] = []
        for cell in cells:
            lab, c = self.cnn.classify_cell(cell)
            if lab in {"blank", "transitioning"}:
                digits.append("?")
                confs.append(c * 0.2)
            else:
                digits.append(lab)
                confs.append(c)
        if all(d == "?" for d in digits):
            return ("", round(float(np.mean(confs) if confs else 0.0), 4))
        text = "".join(digits)
        if self.decimals > 0 and "?" not in text and len(text) > self.decimals:
            text = f"{text[: -self.decimals]}.{text[-self.decimals :]}"
        return (text, round(float(np.mean(confs)), 4))
