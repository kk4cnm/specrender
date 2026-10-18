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
    label_px: float = 0.0,
) -> list[float]:
    """Pick tick frequencies (Hz, ascending) for an axis ``axis_px`` pixels tall.

    Every pair of returned labels is at least ``min_gap_px`` apart on screen,
    so labels never overlap, whatever the scale. That matters most on mel,
    where the spacing between 20, 50 and 100 Hz shrinks to a few pixels.

    ``label_px`` is the label height when the renderer keeps labels inside the
    axis (the HTML player does). A label is then centred no closer than half
    its height to either end, and spacing is measured between those clamped
    centres, not the raw tick positions.
    """
    if not fmax > fmin or axis_px <= 0:
        return []
    lo, hi = _to_scale(fmin, scale), _to_scale(fmax, scale)
    half = min(label_px / 2.0, axis_px / 2.0)

    def px(f: float) -> float:
        y = float((_to_scale(f, scale) - lo) / (hi - lo) * axis_px)
        return min(max(y, half), axis_px - half)

    if scale == "linear":
        return _linear_ticks(fmin, fmax, axis_px, min_gap_px, max_ticks, px)

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


def _linear_ticks(fmin, fmax, axis_px, min_gap_px, max_ticks, px) -> list[float]:
    """Evenly spaced round ticks (1/2/2.5/5 x 10^n) whose labels are >= ``min_gap_px`` apart.

    Counts are computed arithmetically and only the retained ticks are built,
    so even a degenerate axis (a few px for 0-22 kHz) costs a few hundred steps.
    """
    span = fmax - fmin

    def grid(step: float) -> tuple[float, int]:          # first tick, number of ticks
        first = math.ceil(fmin / step - 1e-9) * step
        return first, int(math.floor((fmax - first) / step + 1e-9)) + 1

    def build(step: float, k: int = 1) -> list[float]:
        first, n = grid(step)
        return [round(first + i * step, 9) for i in range(0, n, k)]

    def spaced(ticks: list[float]) -> bool:
        ys = [px(t) for t in ticks]
        return all(abs(b - a) >= min_gap_px - 1e-9 for a, b in zip(ys, ys[1:]))

    # Only steps that could give >= 2 ticks and <= a few hundred are worth trying
    steps = [m * 10.0 ** d for d in range(-3, 9) for m in (1, 2, 2.5, 5)]
    steps = [st for st in steps if span / st <= 1000]

    # Prefer roomy spacing; fall back to the bare minimum if that leaves < 2 ticks
    for spacing in (1.8 * min_gap_px, min_gap_px):
        for st in steps:
            if st / span * axis_px < spacing:
                continue
            _, n = grid(st)
            if n > max_ticks:
                continue
            t = build(st)
            if len(t) >= 2 and spaced(t):
                return t
            if len(t) >= 2:
                continue          # end labels clamped together; try a coarser step
            break                 # one tick at this step: coarser steps can't do better
    # Very short axis: every round step is either too dense or leaves one tick.
    # Take a finer step and keep every k-th tick (stride computed, not filtered).
    for st in reversed(steps):
        _, n = grid(st)
        if n < 2:
            continue
        k = max(1, math.ceil(min_gap_px / (st / span * axis_px)))
        if (n + k - 1) // k >= 2:
            t = build(st, k)[:max_ticks]
            if spaced(t):
                return t
    # Not even two labels fit: show the roundest value nearest the middle
    mid = (fmin + fmax) / 2.0
    for st in reversed(steps):                       # coarsest step that fits the range
        v = round(round(mid / st) * st, 9)
        if st <= span and fmin <= v <= fmax:
            return [v]
    return []


def _mantissa(f: float) -> int:
    return int(round(f / 10 ** math.floor(math.log10(f))))
