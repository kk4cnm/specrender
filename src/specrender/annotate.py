"""Annotated rendering (axes, labels, colorbar) via matplotlib."""
from __future__ import annotations

import io
from typing import TYPE_CHECKING, Optional

import numpy as np
from PIL import Image

if TYPE_CHECKING:
    from .core import Spectrogram


def _fmt_hz(f: float) -> str:
    if f >= 1000:
        k = f / 1000.0
        return f"{k:.0f}k" if abs(k - round(k)) < 1e-6 else f"{k:g}k"
    return f"{f:g}"


def _fmt_time(t: float, total: float) -> str:
    if total >= 120:
        m, s = divmod(t, 60)
        h, m = divmod(int(m), 60)
        return f"{h}:{m:02d}:{s:02.0f}" if h else f"{m}:{s:02.0f}"
    return f"{t:g}"


def render_annotated(
    spec: "Spectrogram",
    levels: np.ndarray,
    lut: np.ndarray,
    *,
    width: int,
    height: int,
    bounds: tuple[float, float],
    title: Optional[str],
    colorbar: bool,
    theme: str,
    dpi: int,
    gap_color: str,
) -> Image.Image:
    try:
        import matplotlib
        from matplotlib.figure import Figure
        from matplotlib.cm import ScalarMappable
        from matplotlib.colors import ListedColormap, Normalize
    except ImportError:
        raise ImportError("annotate=True requires matplotlib: pip install specrender[annotate]") from None

    import matplotlib.font_manager  # noqa: F401  (rcParams font size -> points)

    from .core import _to_scale
    from .ticks import freq_ticks

    fg, bg = ("#d8d8d8", "#111111") if theme == "dark" else ("#222222", "#ffffff")
    C = levels.shape[0]
    t0 = spec.start
    t1 = spec.start + spec.duration
    s_lo, s_hi = _to_scale(spec.fmin, spec.scale), _to_scale(spec.fmax, spec.scale)
    cmap = ListedColormap(lut / 255.0)

    with matplotlib.rc_context({
        "text.color": fg, "axes.labelcolor": fg, "xtick.color": fg, "ytick.color": fg,
        "axes.edgecolor": fg, "figure.facecolor": bg, "axes.facecolor": gap_color,
        "font.size": max(7, min(11, height / 55)),
    }):
        # Figure (not pyplot) so we never touch the caller's GUI backend
        fig = Figure(figsize=(width / dpi, height / dpi), dpi=dpi, layout="constrained")
        axes = fig.subplots(C, 1, sharex=True, squeeze=False)
        for c, ax in enumerate(axes[:, 0]):
            ax.imshow(levels[c], origin="lower", aspect="auto", cmap=cmap, vmin=0, vmax=1,
                      extent=(t0, t1, 0, 1), interpolation="antialiased")
            ax.set_ylabel("Hz" if C == 1 else f"ch{c} Hz")
        last = axes[-1, 0]
        last.set_xlabel("Time" if spec.duration >= 120 else "Time (s)")
        last.xaxis.set_major_formatter(lambda v, _: _fmt_time(v, spec.duration))
        if title:
            fig.suptitle(title)
        if colorbar:
            sm = ScalarMappable(norm=Normalize(*bounds), cmap=cmap)
            cb = fig.colorbar(sm, ax=axes[:, 0].tolist(), pad=0.01, fraction=0.04)
            cb.set_label("dBFS")

        # Frequency ticks depend on the axes' real pixel height, known only after layout.
        # Keep labels at least ~1.5 line-heights apart so they never collide.
        fig.draw_without_rendering()
        axis_px = axes[0, 0].get_window_extent().height
        font_px = matplotlib.rcParams["ytick.labelsize"]
        font_px = (matplotlib.font_manager.FontProperties(size=font_px).get_size_in_points()) * dpi / 72.0
        ticks = freq_ticks(spec.fmin, spec.fmax, spec.scale, axis_px, min_gap_px=max(8.0, 1.5 * font_px))
        tick_pos = (_to_scale(np.array(ticks), spec.scale) - s_lo) / (s_hi - s_lo) if ticks else []
        for ax in axes[:, 0]:
            ax.set_yticks(tick_pos, [_fmt_hz(t) for t in ticks])
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=dpi, facecolor=bg)

    img = Image.open(io.BytesIO(buf.getvalue())).convert("RGB")
    if img.size != (width, height):  # guard against rounding of figsize*dpi
        img = img.resize((width, height), Image.Resampling.LANCZOS)
    return img
