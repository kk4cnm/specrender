"""Color palettes for spectrogram rendering.

Every palette resolves to a 256x3 uint8 lookup table (LUT). Index 0 is the
quietest level, index 255 the loudest.

Palette sources, in lookup order:
  1. Palettes registered with :func:`register_palette`
  2. Built-in palettes (no matplotlib required)
  3. Any matplotlib colormap name, if matplotlib is installed
Append ``_r`` to any name to reverse it.
"""
from __future__ import annotations

from typing import Iterable, Sequence, Union

import numpy as np

ColorLike = Union[str, Sequence[float], Sequence[int]]
PaletteLike = Union[str, Sequence[ColorLike], np.ndarray]

# Control points sampled from well-known colormaps; interpolated to 256 steps.
_BUILTIN: dict[str, list[str]] = {
    # Perceptually uniform (from matplotlib / BIDS)
    "viridis": ["#440154", "#482878", "#3e4989", "#31688e", "#26828e",
                "#1f9e89", "#35b779", "#6ece58", "#b5de2b", "#fde725"],
    "magma": ["#000004", "#180f3d", "#440f76", "#721f81", "#9e2f7f",
              "#cd4071", "#f1605d", "#fd9668", "#feca8d", "#fcfdbf"],
    "inferno": ["#000004", "#1b0c41", "#4a0c6b", "#781c6d", "#a52c60",
                "#cf4446", "#ed6925", "#fb9b06", "#f7d13d", "#fcffa4"],
    "plasma": ["#0d0887", "#46039f", "#7201a8", "#9c179e", "#bd3786",
               "#d8576b", "#ed7953", "#fb9f3a", "#fdca26", "#f0f921"],
    # Color-vision-deficiency friendly
    "cividis": ["#00224e", "#123570", "#3b496c", "#575d6d", "#707173",
                "#8a8678", "#a59c74", "#c3b369", "#e1cc55", "#fee838"],
    # Classic audio-editor / SDR waterfall looks
    "classic": ["#000000", "#000050", "#5000a0", "#c00060", "#ff4000",
                "#ffc000", "#ffffff"],
    "waterfall": ["#000020", "#0000c8", "#00c8ff", "#00ff60", "#ffff00",
                  "#ff8000", "#ff0000"],
    "ice": ["#000000", "#0b1a3a", "#1f4e8c", "#3fa0d0", "#a8e6f0", "#ffffff"],
    "fire": ["#000000", "#5a0000", "#b41e00", "#f06400", "#ffc832", "#ffffff"],
    "green": ["#000000", "#003300", "#00801a", "#33cc33", "#b3ffb3"],
    "gray": ["#000000", "#ffffff"],
    "grey": ["#000000", "#ffffff"],
}

_CUSTOM: dict[str, np.ndarray] = {}


def _parse_color(c: ColorLike) -> tuple[float, float, float]:
    if isinstance(c, str):
        s = c.strip().lstrip("#")
        if len(s) == 3:
            s = "".join(ch * 2 for ch in s)
        if len(s) not in (6, 8):
            raise ValueError(f"Unrecognized color {c!r}; use '#rrggbb' or an RGB tuple")
        return tuple(int(s[i:i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]
    vals = [float(v) for v in c][:3]
    if len(vals) != 3:
        raise ValueError(f"Color {c!r} needs 3 components")
    if max(vals) > 1.0:  # treat as 0-255
        vals = [v / 255.0 for v in vals]
    return tuple(vals)  # type: ignore[return-value]


def lut_from_colors(colors: Iterable[ColorLike], n: int = 256) -> np.ndarray:
    """Build an ``(n, 3)`` uint8 LUT by evenly interpolating the given colors."""
    rgb = np.array([_parse_color(c) for c in colors], dtype=np.float64)
    if len(rgb) == 0:
        raise ValueError("A palette needs at least one color")
    if len(rgb) == 1:
        rgb = np.vstack([np.zeros(3), rgb[0]])
    xp = np.linspace(0.0, 1.0, len(rgb))
    x = np.linspace(0.0, 1.0, n)
    out = np.stack([np.interp(x, xp, rgb[:, k]) for k in range(3)], axis=1)
    return np.clip(np.round(out * 255.0), 0, 255).astype(np.uint8)


def register_palette(name: str, colors: Union[Sequence[ColorLike], np.ndarray]) -> None:
    """Register a named palette from a list of colors or an (N, 3) array."""
    _CUSTOM[name.lower()] = get_palette(colors)


def list_palettes(include_matplotlib: bool = False) -> list[str]:
    """Names usable as ``palette=``. Every name also accepts an ``_r`` suffix."""
    names = set(_BUILTIN) | set(_CUSTOM)
    if include_matplotlib:
        try:
            import matplotlib
            names |= {n for n in matplotlib.colormaps if not n.endswith("_r")}
        except ImportError:
            pass
    return sorted(names)


def get_palette(palette: PaletteLike) -> np.ndarray:
    """Resolve a palette spec to a ``(256, 3)`` uint8 LUT.

    ``palette`` may be a name (``"magma"``, ``"gray_r"``), a list of colors
    (hex strings or RGB tuples), or an
    existing ``(N, 3)`` array (uint8 0-255 or float 0-1).
    """
    if isinstance(palette, np.ndarray):
        arr = np.asarray(palette)
        if arr.ndim != 2 or arr.shape[1] < 3:
            raise ValueError("Palette arrays must have shape (N, 3)")
        arr = arr[:, :3].astype(np.float64)
        if arr.max() <= 1.0:
            arr = arr * 255.0
        return lut_from_colors([tuple(row) for row in arr / 255.0])

    if not isinstance(palette, str):
        return lut_from_colors(palette)

    name = palette.strip().lower()
    reverse = name.endswith("_r")
    base = name[:-2] if reverse else name

    if base in _CUSTOM:
        lut = _CUSTOM[base]
    elif base in _BUILTIN:
        lut = lut_from_colors(_BUILTIN[base])
    else:
        lut = _matplotlib_lut(palette[:-2] if reverse else palette)
    return lut[::-1].copy() if reverse else lut


def _matplotlib_lut(name: str) -> np.ndarray:
    try:
        import matplotlib
    except ImportError:
        raise ValueError(
            f"Unknown palette {name!r}. Built-ins: {', '.join(list_palettes())}. "
            "Install matplotlib to use its colormaps too."
        ) from None
    try:
        cmap = matplotlib.colormaps[name]
    except KeyError:
        raise ValueError(
            f"Unknown palette {name!r}. Built-ins: {', '.join(list_palettes())}"
        ) from None
    rgba = cmap(np.linspace(0.0, 1.0, 256))
    return np.clip(np.round(rgba[:, :3] * 255.0), 0, 255).astype(np.uint8)
