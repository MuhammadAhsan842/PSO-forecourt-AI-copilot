"""Rollover carry + rolling-digit prediction from the flow prior.

A digit has no language dictionary. The monotonic fill replaces it: a 9 that
rolls must carry, and a transitioning cell should match the rate-predicted digit.
"""

from __future__ import annotations


def predicted_digits(litres: float, *, num_digits: int, decimals: int) -> list[str]:
    scale = 10 ** max(0, int(decimals))
    n = round(max(0.0, float(litres)) * scale)
    s = str(n).zfill(num_digits)
    return list(s[-num_digits:])


def apply_transition_and_carry(
    labels: list[str],
    *,
    predicted: list[str] | None = None,
) -> tuple[list[str], list[str]]:
    """Replace transitioning/? cells with the rate-predicted digit; check 9→0 carry."""
    flags: list[str] = []
    out = list(labels)
    if predicted and len(predicted) == len(out):
        for i, lab in enumerate(out):
            if lab in {"transitioning", "?", "blank", ""}:
                out[i] = predicted[i]
                flags.append("transition_predicted")
        # Right-to-left carry consistency vs prediction.
        for i in range(len(out) - 1, 0, -1):
            if (
                labels[i] in {"0", "transitioning", "?"}
                and predicted[i] == "0"
                and predicted[i - 1] != out[i - 1]
                and labels[i - 1] in {"9", "transitioning", "?"}
            ):
                out[i - 1] = predicted[i - 1]
                flags.append("rollover_carry")
    return out, flags
