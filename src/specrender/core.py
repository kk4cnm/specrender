"""Spectrogram computation and rendering."""
from __future__ import annotations

import inspect
import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional, Sequence, Union

import numpy as np
from PIL import Image

from .audio import PathLike, load_audio
from .palettes import PaletteLike, get_palette

Scale = Literal["linear", "log", "mel"]
Aggregate = Literal["max", "mean"]
ChannelSpec = Union[str, int]
Source = Union[PathLike, np.ndarray]

_AMIN = 1e-20  # power floor, ~-200 dBFS
_BLOCK_FRAMES = 2048  # STFT frames per processing block (bounds memory)


# --------------------------------------------------------------------------- #
# Frequency scales
# --------------------------------------------------------------------------- #
def _to_scale(f: np.ndarray, scale: Scale) -> np.ndarray:
    f = np.asarray(f, dtype=np.float64)
    if scale == "linear":
        return f
    if scale == "log":
        return np.log(np.maximum(f, 1e-9))
    if scale == "mel":
        return 2595.0 * np.log10(1.0 + f / 700.0)
    raise ValueError(f"scale must be 'linear', 'log' or 'mel', not {scale!r}")


def _from_scale(v: np.ndarray, scale: Scale) -> np.ndarray:
    v = np.asarray(v, dtype=np.float64)
    if scale == "linear":
        return v
    if scale == "log":
        return np.exp(v)
    return 700.0 * (10.0 ** (v / 2595.0) - 1.0)


class _FreqMapper:
    """Maps FFT bins onto ``rows`` output rows evenly spaced on a frequency scale.

    Rows covering several bins take the max (or mean) of those bins, so narrow
    tones survive downscaling. Rows narrower than one bin interpolate.
    """

    def __init__(self, bin_freqs, fmin, fmax, rows, scale, aggregate):
        edges = _from_scale(
            np.linspace(_to_scale(fmin, scale), _to_scale(fmax, scale), rows + 1), scale
        )
        self.centers = _from_scale(
            (_to_scale(edges[:-1], scale) + _to_scale(edges[1:], scale)) / 2, scale
        )
        self.aggregate = aggregate
        starts = np.searchsorted(bin_freqs, edges[:-1], side="left")
        stops = np.searchsorted(bin_freqs, edges[1:], side="left")
        stops[-1] = np.searchsorted(bin_freqs, edges[-1], side="right")
        stops = np.maximum(stops, starts)
        counts = stops - starts
        self.full = np.nonzero(counts > 0)[0]
        self.empty = np.nonzero(counts == 0)[0]
        if len(self.full):
            self.lo = int(starts[self.full[0]])
            self.hi = int(stops[self.full[-1]])
            self.idx = starts[self.full] - self.lo
            self.counts = counts[self.full].astype(np.float32)
        # Linear interpolation weights for rows narrower than a bin
        c = self.centers[self.empty]
        i1 = np.clip(np.searchsorted(bin_freqs, c), 1, len(bin_freqs) - 1)
        i0 = i1 - 1
        span = bin_freqs[i1] - bin_freqs[i0]
        self.i0, self.i1 = i0, i1
        self.w = np.clip((c - bin_freqs[i0]) / np.where(span > 0, span, 1), 0, 1).astype(np.float32)
        self.rows = rows

    def __call__(self, p: np.ndarray) -> np.ndarray:
        """``p``: (frames, bins) power -> (frames, rows)."""
        out = np.empty((p.shape[0], self.rows), dtype=np.float32)
        if len(self.full):
            seg = p[:, self.lo:self.hi]
            if self.aggregate == "max":
                out[:, self.full] = np.maximum.reduceat(seg, self.idx, axis=1)
            else:
                out[:, self.full] = np.add.reduceat(seg, self.idx, axis=1) / self.counts
        if len(self.empty):
            out[:, self.empty] = p[:, self.i0] * (1 - self.w) + p[:, self.i1] * self.w
        return out


# --------------------------------------------------------------------------- #
# Result object
# --------------------------------------------------------------------------- #
@dataclass
class Spectrogram:
    """A computed spectrogram in dBFS, ready to be rendered any number of ways.

    Attributes:
        db: ``(channels, rows, cols)`` levels in dBFS. Row 0 is the lowest frequency.
        freqs: Center frequency (Hz) of each row.
        times: Center time (s, relative to the source file) of each column.
        sample_rate: Sample rate of the analysed audio.
        scale: Frequency scale of the rows.
        fmin, fmax: Frequency range covered.
    """

    db: np.ndarray
    freqs: np.ndarray
    times: np.ndarray
    sample_rate: int
    scale: Scale
    fmin: float
    fmax: float
    duration: float
    start: float = 0.0
    params: dict = field(default_factory=dict)

    @property
    def channels(self) -> int:
        return self.db.shape[0]

    def levels(
        self,
        dynamic_range: float = 80.0,
        db_range: Optional[tuple[float, float]] = None,
        gamma: float = 1.0,
    ) -> np.ndarray:
        """Normalized 0..1 levels. ``db_range=(lo, hi)`` in dBFS fixes the scale
        (useful for comparing files); otherwise the top is the loudest point and
        the bottom is ``dynamic_range`` dB below it."""
        lo, hi = self.level_bounds(dynamic_range, db_range)
        v = np.clip((self.db - lo) / (hi - lo), 0.0, 1.0)
        if gamma != 1.0:
            v = v ** (1.0 / gamma)
        return v.astype(np.float32)

    def level_bounds(self, dynamic_range=80.0, db_range=None) -> tuple[float, float]:
        if db_range is not None:
            lo, hi = map(float, db_range)
        else:
            hi = float(self.db.max())
            lo = hi - float(dynamic_range)
        if hi <= lo:
            raise ValueError("db_range must be (low, high) with high > low")
        return lo, hi

    def to_image(
        self,
        *,
        width: Optional[int] = None,
        height: Optional[int] = None,
        palette: PaletteLike = "magma",
        dynamic_range: float = 80.0,
        db_range: Optional[tuple[float, float]] = None,
        gamma: float = 1.0,
        channel_gap: int = 2,
        gap_color: str = "#000000",
        annotate: bool = False,
        title: Optional[str] = None,
        colorbar: bool = True,
        theme: Literal["dark", "light"] = "dark",
        dpi: int = 100,
    ) -> Image.Image:
        """Render to a PIL RGB image of exactly ``width`` x ``height`` pixels.

        ``annotate=True`` adds time/frequency axes, title and a dB colorbar
        (requires matplotlib); the whole figure is then ``width`` x ``height``.
        """
        lut = get_palette(palette)
        lv = self.levels(dynamic_range, db_range, gamma)
        # Default to the size requested at compute() time, if any
        width = width if width is not None else self.params.get("width")
        height = height if height is not None else self.params.get("height")

        if annotate:
            from .annotate import render_annotated

            return render_annotated(
                self, lv, lut, width=width or 1200, height=height or 600,
                bounds=self.level_bounds(dynamic_range, db_range),
                title=title, colorbar=colorbar, theme=theme, dpi=dpi,
                gap_color=gap_color,
            )

        C, rows, cols = lv.shape
        W = int(width or cols)
        if height is None:
            per = [rows] * C
            gaps = [channel_gap] * (C - 1)
        else:
            per, gaps = _split_height(int(height), C, channel_gap)

        gap_rgb = np.array(_hex(gap_color), dtype=np.uint8)
        parts = []
        for c in range(C):
            chan = lv[c, ::-1]  # low frequencies at the bottom
            if chan.shape != (per[c], W):
                chan = _resize_float(chan, W, per[c])
            idx = np.clip(np.rint(chan * 255.0), 0, 255).astype(np.uint8)
            parts.append(lut[idx])
            if c < C - 1 and gaps[c] > 0:
                parts.append(np.broadcast_to(gap_rgb, (gaps[c], W, 3)))
        return Image.fromarray(np.ascontiguousarray(np.concatenate(parts, axis=0)), "RGB")

    def save(self, path: PathLike, *, format: Optional[str] = None, quality: int = 92,
             **image_kwargs) -> Path:
        """Render with :meth:`to_image` options and write to ``path``."""
        return save_image(self.to_image(**image_kwargs), path, format=format, quality=quality)

    def to_bytes(self, format: str = "PNG", *, quality: int = 92, **image_kwargs) -> bytes:
        """Render and encode in memory, e.g. for an HTTP response."""
        buf = io.BytesIO()
        _write(self.to_image(**image_kwargs), buf, format, quality)
        return buf.getvalue()


# --------------------------------------------------------------------------- #
# Computation
# --------------------------------------------------------------------------- #
def compute(
    source: Source,
    *,
    sample_rate: Optional[int] = None,
    channel: ChannelSpec = "mix",
    start: float = 0.0,
    end: Optional[float] = None,
    n_fft: int = 2048,
    hop_length: Optional[int] = None,
    window: Union[str, tuple] = "hann",
    scale: Scale = "linear",
    fmin: Optional[float] = None,
    fmax: Optional[float] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
    channel_gap: int = 2,
    aggregate: Aggregate = "max",
    pre_emphasis: float = 0.0,
) -> Spectrogram:
    """Compute a spectrogram from a file path or a numpy array.

    Args:
        source: Path to an audio file, or an array of shape ``(n,)`` or
            ``(channels, n)``; arrays require ``sample_rate``.
        sample_rate: Resample files to this rate, or the rate of an array source.
        channel: ``"mix"`` (mono downmix), ``"left"``, ``"right"``, ``"side"``
            (L-R difference), an integer channel index, or ``"all"`` to stack
            every channel vertically.
        start, end: Time window to analyse, in seconds.
        n_fft: FFT size. Larger = finer frequency detail, blurrier time detail.
        hop_length: Samples between frames (default ``n_fft // 4``).
        window: Any ``scipy.signal.get_window`` spec.
        scale: Frequency axis: ``"linear"``, ``"log"`` or ``"mel"``.
        fmin, fmax: Frequency range in Hz (defaults: 0 or 20 Hz, Nyquist).
        width, height: Target pixel size. Used to pool long files down to
            ``width`` columns while streaming (bounded memory) and to map bins
            onto exactly ``height`` rows.
        aggregate: How bins/frames are combined when downscaling: ``"max"``
            keeps narrow tones and short clicks visible; ``"mean"`` is smoother.
        pre_emphasis: First-order high-pass coefficient (e.g. 0.97 for speech).
    """
    if aggregate not in ("max", "mean"):
        raise ValueError("aggregate must be 'max' or 'mean'")
    if n_fft < 16:
        raise ValueError("n_fft must be >= 16")
    hop = int(hop_length or max(1, n_fft // 4))

    x, sr = _resolve_source(source, sample_rate, start, end)
    x = _select_channels(x, channel)
    if pre_emphasis:
        x = np.concatenate([x[:, :1], x[:, 1:] - pre_emphasis * x[:, :-1]], axis=1)
    C, n = x.shape
    if n == 0:
        raise ValueError("No audio samples in the selected range")

    nyq = sr / 2.0
    fmax_ = float(min(fmax if fmax is not None else nyq, nyq))
    fmin_ = float(fmin if fmin is not None else (0.0 if scale == "linear" else max(20.0, sr / n_fft)))
    if scale == "log" and fmin_ <= 0:
        raise ValueError("Log scale needs fmin > 0")
    if not 0 <= fmin_ < fmax_:
        raise ValueError(f"Invalid frequency range {fmin_}..{fmax_} Hz")

    from scipy.signal import get_window

    win = get_window(window, n_fft, fftbins=True).astype(np.float32)
    full_scale_power = (win.sum() / 2.0) ** 2  # |X|^2 of a 0 dBFS sine
    bin_freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)

    # Rows
    if height is not None:
        rows = _split_height(int(height), C, channel_gap)[0][0]
    elif scale == "linear":
        rows = int(np.count_nonzero((bin_freqs >= fmin_) & (bin_freqs <= fmax_)))
    else:
        rows = 512
    rows = max(rows, 1)
    if height is None and scale == "linear":
        sel = np.nonzero((bin_freqs >= fmin_) & (bin_freqs <= fmax_))[0]
        lo_b, hi_b = int(sel[0]), int(sel[-1]) + 1
        mapper = lambda p: p[:, lo_b:hi_b]  # noqa: E731  native bins
        row_freqs = bin_freqs[lo_b:hi_b]
    else:
        fm = _FreqMapper(bin_freqs, fmin_, fmax_, rows, scale, aggregate)
        mapper, row_freqs = fm, fm.centers

    # Frames
    pad = n_fft // 2
    n_frames = 1 + max(0, (n + 2 * pad - n_fft) // hop)
    pool_to = int(width) if (width and n_frames >= 2 * int(width)) else None
    cols = pool_to or n_frames

    from scipy import fft as sfft

    out = np.empty((C, rows, cols), dtype=np.float32)
    for c in range(C):
        xp = np.pad(x[c], (pad, pad + n_fft))
        frames = np.lib.stride_tricks.sliding_window_view(xp, n_fft)[::hop][:n_frames]
        acc = np.full((cols, rows), 0.0, dtype=np.float32)
        if pool_to:
            col_of = (np.arange(n_frames) * cols // n_frames).astype(np.intp)
            counts = np.bincount(col_of, minlength=cols).astype(np.float32)
        for b in range(0, n_frames, _BLOCK_FRAMES):
            blk = frames[b:b + _BLOCK_FRAMES] * win
            spec = sfft.rfft(blk, axis=1, workers=-1)
            p = mapper((spec.real ** 2 + spec.imag ** 2).astype(np.float32))
            if not pool_to:
                acc[b:b + len(p)] = p
            elif aggregate == "max":
                np.maximum.at(acc, col_of[b:b + len(p)], p)
            else:
                np.add.at(acc, col_of[b:b + len(p)], p)
        if pool_to and aggregate == "mean":
            acc /= counts[:, None]
        out[c] = acc.T

    db = 10.0 * np.log10(np.maximum(out, _AMIN * full_scale_power) / full_scale_power)
    frame_t = np.arange(n_frames) * hop / sr
    if pool_to:
        edges = np.linspace(0, n_frames, cols + 1)
        times = ((edges[:-1] + edges[1:]) / 2 - 0.5) * hop / sr
    else:
        times = frame_t
    return Spectrogram(
        db=db.astype(np.float32), freqs=np.asarray(row_freqs, dtype=np.float64),
        times=times + start, sample_rate=sr, scale=scale, fmin=fmin_, fmax=fmax_,
        duration=n / sr, start=start,
        params=dict(n_fft=n_fft, hop_length=hop, window=window, channel=channel,
                    aggregate=aggregate, width=width, height=height,
                    channel_gap=channel_gap),
    )


def render(
    source: Union[Source, Spectrogram],
    output: Optional[PathLike] = None,
    *,
    format: Optional[str] = None,
    quality: int = 92,
    **kwargs,
) -> Image.Image:
    """One call: compute, render and optionally save.

    Accepts every keyword of :func:`compute` and :meth:`Spectrogram.to_image`.
    Returns the PIL image (also written to ``output`` if given).
    """
    compute_keys, image_keys = _compute_keys(), _image_keys()
    unknown = set(kwargs) - compute_keys - image_keys
    if unknown:
        raise TypeError(f"Unknown option(s): {', '.join(sorted(unknown))}")

    if isinstance(source, Spectrogram):
        spec = source
    else:
        spec = compute(source, **{k: v for k, v in kwargs.items() if k in compute_keys})
    img = spec.to_image(**{k: v for k, v in kwargs.items() if k in image_keys})
    if output is not None:
        save_image(img, output, format=format, quality=quality)
    return img


def render_batch(
    sources: Sequence[PathLike],
    out_dir: PathLike,
    *,
    format: str = "png",
    quality: int = 92,
    shared_levels: bool = False,
    dynamic_range: float = 80.0,
    **kwargs,
) -> list[Path]:
    """Render many files into ``out_dir`` as ``<stem>.<format>``.

    ``shared_levels=True`` puts every image on the same dB scale (top = loudest
    point across all files) so brightness is comparable between images.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    compute_keys = _compute_keys()
    ckw = {k: v for k, v in kwargs.items() if k in compute_keys}
    ikw = {k: v for k, v in kwargs.items() if k not in compute_keys}
    for k in ("width", "height", "channel_gap"):
        if k in ckw:
            ikw[k] = ckw[k]

    specs = [compute(s, **ckw) for s in sources] if shared_levels else None
    if shared_levels and "db_range" not in ikw:
        hi = max(float(s.db.max()) for s in specs)
        ikw["db_range"] = (hi - dynamic_range, hi)

    written = []
    for i, src in enumerate(sources):
        spec = specs[i] if specs else compute(src, **ckw)
        path = out_dir / f"{Path(src).stem}.{format.lower().lstrip('.')}"
        written.append(spec.save(path, quality=quality, dynamic_range=dynamic_range, **ikw))
    return written


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #
_EXT_FORMATS = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP",
                ".bmp": "BMP", ".tif": "TIFF", ".tiff": "TIFF", ".gif": "GIF"}


def save_image(img: Image.Image, path: PathLike, *, format: Optional[str] = None,
               quality: int = 92) -> Path:
    """Save with the format taken from ``format`` or the file extension."""
    path = Path(path)
    fmt = (format or _EXT_FORMATS.get(path.suffix.lower()) or "").upper()
    if not fmt:
        raise ValueError(f"Can't infer image format from {path.name!r}; pass format=")
    fmt = "JPEG" if fmt == "JPG" else fmt
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as fh:
        _write(img, fh, fmt, quality)
    return path


def _write(img: Image.Image, fh, fmt: str, quality: int) -> None:
    fmt = fmt.upper()
    fmt = "JPEG" if fmt == "JPG" else fmt
    if fmt in ("JPEG", "BMP") and img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    opts: dict = {}
    if fmt in ("JPEG", "WEBP"):
        opts["quality"] = int(quality)
    if fmt == "JPEG":
        opts["subsampling"] = 0  # keep thin colored lines crisp
    if fmt == "PNG":
        opts["optimize"] = True
    img.save(fh, format=fmt, **opts)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _compute_keys() -> set[str]:
    return set(list(inspect.signature(compute).parameters)[1:])


def _image_keys() -> set[str]:
    return set(list(inspect.signature(Spectrogram.to_image).parameters)[1:])


def _resolve_source(source, sample_rate, start, end) -> tuple[np.ndarray, int]:
    if isinstance(source, np.ndarray):
        if not sample_rate:
            raise ValueError("sample_rate is required when source is an array")
        x = np.asarray(source, dtype=np.float32)
        if x.ndim == 1:
            x = x[None, :]
        elif x.ndim == 2 and x.shape[0] > x.shape[1]:
            x = x.T  # accept (n, channels)
        elif x.ndim != 2:
            raise ValueError("Array source must be (n,) or (channels, n)")
        sr = int(sample_rate)
        a = int(round(start * sr))
        b = None if end is None else int(round(end * sr))
        return x[:, a:b], sr
    return load_audio(source, start=start, end=end, sample_rate=sample_rate)


def _select_channels(x: np.ndarray, channel: ChannelSpec) -> np.ndarray:
    C = x.shape[0]
    if channel in ("mix", "mid", "mono"):
        return x.mean(axis=0, keepdims=True)
    if channel in ("all", "stack"):
        return x
    if channel == "side":
        if C < 2:
            raise ValueError("'side' needs a stereo source")
        return (x[0:1] - x[1:2]) / 2.0
    idx = {"left": 0, "l": 0, "right": 1, "r": 1}.get(channel, channel)  # type: ignore[arg-type]
    if not isinstance(idx, (int, np.integer)):
        raise ValueError(f"Unknown channel spec {channel!r}")
    if C == 1 and idx in (0, 1):
        return x
    if not -C <= idx < C:
        raise ValueError(f"Channel {channel!r} not available ({C} channel(s))")
    return x[idx:idx + 1] if idx != -1 else x[-1:]


def _split_height(height: int, channels: int, gap: int) -> tuple[list[int], list[int]]:
    gap = max(0, gap) if channels > 1 else 0
    per = (height - gap * (channels - 1)) // channels
    if per < 1:
        raise ValueError(f"height={height} too small for {channels} channels")
    spare = height - per * channels
    gaps = [spare // (channels - 1) + (1 if i < spare % (channels - 1) else 0)
            for i in range(channels - 1)] if channels > 1 else []
    return [per] * channels, gaps


def _resize_float(a: np.ndarray, w: int, h: int) -> np.ndarray:
    im = Image.fromarray(np.ascontiguousarray(a, dtype=np.float32), "F")
    shrink = w < a.shape[1] or h < a.shape[0]
    im = im.resize((w, h), Image.Resampling.BOX if shrink else Image.Resampling.BILINEAR)
    return np.asarray(im, dtype=np.float32)


def _hex(c: str) -> tuple[int, int, int]:
    s = c.lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
