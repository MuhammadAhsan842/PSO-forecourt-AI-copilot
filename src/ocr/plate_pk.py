"""Pakistani number-plate normalisation & format validation (Milestone 10).

Generic OCR fails on local plates (§5), so two things make a raw read usable:

  1. **Normalisation** — uppercase, drop separators/whitespace, and repair the
     handful of OCR confusions that are safe *given the position* in the plate
     (letters-then-digits): an ``O`` in the digit block is a ``0``; a ``1`` in the
     letter block is an ``I``. We never "correct" a character we can't place.
  2. **Format validation** — match against the province formats actually seen in
     Punjab/ICT so a plausible plate is accepted and a garbage read is flagged
     low-trust rather than silently linked to a sale.

This is deterministic and testable now. A plate model fine-tuned on Pakistani
plates raises raw-character accuracy later; it feeds these same rules unchanged.
"""

from __future__ import annotations

import re

# Formats seen locally. Kept as anchored regexes so validation is exact.
#   LEA-1234 / LEB-19-1234 (Punjab)   ABC-123 (older)   ICT: e.g. AJK / capital series
PK_PLATE_PATTERNS: tuple[str, ...] = (
    r"^[A-Z]{2,3}[0-9]{2,4}$",          # LEA1234, ABC123
    r"^[A-Z]{2,3}[0-9]{2}[0-9]{3,4}$",  # LEB19 1234 (area-year-serial, separators stripped)
    r"^[A-Z]{1,2}[0-9]{3,4}$",          # older short series
)

# Position-aware OCR confusion repairs.
_LETTER_FIXES = {"0": "O", "1": "I", "5": "S", "8": "B", "2": "Z", "6": "G"}
_DIGIT_FIXES = {"O": "0", "I": "1", "L": "1", "S": "5", "B": "8", "Z": "2", "G": "6", "Q": "0"}


def _split_at(s: str, boundary: int) -> str:
    letters = "".join(c if c.isalpha() else _LETTER_FIXES.get(c, c) for c in s[:boundary])
    digits = "".join(c if c.isdigit() else _DIGIT_FIXES.get(c, c) for c in s[boundary:])
    return letters + digits


def normalize_plate(raw: str) -> str:
    """Uppercase, strip non-alphanumerics, and apply position-aware repairs.

    Assumes the local letters-then-digits layout: a leading alpha block followed
    by a numeric block. We pick the letter/digit boundary that yields a *valid*
    plate (preferring a 2–3 char letter block); if none validates we fall back to
    the leading run of true letters. Characters are only repaired in the block
    where their corrected form belongs, so we never invent an implausible plate.
    """
    if not raw:
        return ""
    s = re.sub(r"[^A-Za-z0-9]", "", raw).upper()
    n = len(s)
    if n < 2:
        return s

    # Trust the leading run of TRUE letters first — an alphabetic character
    # belongs in the letter block and must not be demoted to a digit (e.g. the
    # 'O' in "LEO" is not a zero). Only when the first character was itself
    # misread (no leading letters) do we search for the best boundary.
    lead = 0
    while lead < n and s[lead].isalpha():
        lead += 1

    order: list[int] = []
    if 2 <= lead < n:
        order.append(lead)
    order += sorted((b for b in range(1, n) if b != lead), key=lambda b: (abs(b - 2), b))

    for b in order:
        out = _split_at(s, b)
        if is_valid_pk_plate(out):
            return out

    # No format matched — keep the leading true-letter run as the boundary so the
    # read stays inspectable rather than being force-fit to a pattern.
    return _split_at(s, max(1, lead))


def is_valid_pk_plate(plate: str) -> bool:
    return any(re.match(p, plate) for p in PK_PLATE_PATTERNS)
