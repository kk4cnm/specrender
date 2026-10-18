"""Frequency-axis tick selection shared by the HTML player and annotated images."""
from __future__ import annotations

import math

from .core import _to_scale

#: Default minimum distance between two frequency labels, in pixels.
#: Fits ~11 px text with a little air.
MIN_GAP_PX = 16.0

# Preference order for log/mel candidates: decades first, then 5s, then 2s.
_MANTISSA_RANK = {1: 0, 5: 1, 2: 2}


def freq_ticks(
    fmin: float,
    fmax: float,
    scale: str,
    axis_px: float,
    *,
    min_gap_px: float = MIN_GAP_PX,
    max_ticks: int = 10,
) -> list[float]:
    """Pick tick frequencies (Hz, ascending) for an axis ``axis_px`` pixels tall.

    Every pair of returned ticks is at least ``min_gap_px`` apart on screen,
    so labels never overlap, whatever the scale. That matters most on mel,
    where the spacing between 20, 50 and 100 Hz shrinks to a few pixels.
    """
    if not fmax > fmin:
        return []
    lo, hi = _to_scale(fmin, scale), _to_scale(fmax, scale)

    def px(f: float) -> float:
        return float((_to_scale(f, scale) - lo) / (hi - lo) * axis_px)

    if scale == "linear":
        return _linear_ticks(fmin, fmax, axis_px, min_gap_px, max_ticks)

    cands = [m * 10.0 ** d for d in range(0, 7) for m in (1, 2, 5)]
    cands = [f for f in cands if fmin - 1e-9 <= f <= fmax + 1e-9]
    # Most important first; among equals, prefer the roomier top of the axis
    order = sorted(cands, key=lambda f: (_MANTISSA_RANK[_mantissa(f)], -f))

    def greedy(seq: list[float]) -> list[float]:
        chosen: list[float] = []
        for f in seq:
            if len(chosen) >= max_ticks:
                break
            if all(abs(px(f) - px(c)) >= min_gap_px for c in chosen):
                chosen.append(f)
        return chosen

    best = greedy(order)
    if len(best) < 2:
        # On short or narrow axes the top-priority tick can block every other one
        # (e.g. 1k between 500 and 2k). Try each start and keep the fullest set.
        for f in order:
            alt = greedy([f] + [g for g in order if g != f])
            if len(alt) > len(best):
                best = alt
    return sorted(best)


def _linear_ticks(fmin: float, fmax: float, axis_px: float, min_gap_px: float, max_ticks: int) -> list[float]:
    """Evenly spaced round ticks (1/2/2.5/5 x 10^n) at least ``min_gap_px`` apart."""
    span = fmax - fmin

    def ticks_for(step: float) -> list[float]:
        first = math.ceil(fmin / step - 1e-9) * step
        n = int(math.floor((fmax - first) / step + 1e-9)) + 1
        return [round(first + i * step, 9) for i in range(n)]

    steps = [m * 10.0 ** d for d in range(-3, 9) for m in (1, 2, 2.5, 5)]
    out: list[float] = []
    # Prefer roomy spacing; fall back to the bare minimum if that leaves < 2 ticks
    for spacing in (1.8 * min_gap_px, min_gap_px):
        for step in steps:
            if step / span * axis_px >= spacing and len(ticks_for(step)) <= max_ticks:
                out = ticks_for(step)
                break
        if len(out) >= 2:
            break
    if len(out) < 2:
        # Very short axis: every round step is either too dense or leaves one tick.
        # Take a finer step and keep every k-th tick so the gap holds (e.g. 1k, 3k).
        for step in reversed(steps):
            t = ticks_for(step)
            if len(t) < 2:
                continue
            k = math.ceil(min_gap_px / (step / span * axis_px))
            if len(t[::k]) >= 2:
                out = t[::k][:max_ticks]
                break
    return out


def _mantissa(f: float) -> int:
    return int(round(f / 10 ** math.floor(math.log10(f))))
