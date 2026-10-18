"""Interactive HTML player: spectrogram + audio with playhead, scrubbing and looping.

Two ways to use it:

* :func:`player` writes **one self-contained HTML file** (spectrogram image,
  audio and player script all inlined). Open it in any browser, email it, or
  attach it.
* :func:`export_player` writes **separate files** (``specrender-player.js``,
  ``<name>.png``, ``<name>.json`` and the audio) for embedding one or more
  players in your own web pages with ``<spectro-player meta="name.json">``.
"""
from __future__ import annotations

import base64
import html
import io
import json
import os
import shutil
import subprocess
import tempfile
import warnings
from importlib import resources
from pathlib import Path
from typing import Literal, Optional, Union
from urllib.parse import quote

import numpy as np

from .annotate import _fmt_hz
from .audio import PathLike, load_audio
from .core import Source, Spectrogram, _compute_keys, _image_keys, _to_scale, compute
from .ticks import freq_ticks

#: Extensions browsers play natively, with their MIME types.
BROWSER_AUDIO = {
    ".mp3": "audio/mpeg", ".wav": "audio/wav", ".wave": "audio/wav", ".ogg": "audio/ogg",
    ".oga": "audio/ogg", ".opus": "audio/ogg", ".flac": "audio/flac", ".m4a": "audio/mp4",
    ".aac": "audio/aac", ".webm": "audio/webm",
}

#: Height of a frequency label in the player (CSS line box). The player keeps
#: labels inside the plot; tick spacing is measured with that clamp applied.
LABEL_PX = 15.0

AudioMode = Literal["auto", "original", "m4a", "mp3", "wav"]


def player_js() -> str:
    """The ``<spectro-player>`` web component source."""
    return resources.files("specrender").joinpath("web/specrender-player.js").read_text(encoding="utf-8")


def player(
    source: Source,
    output: Optional[PathLike] = None,
    *,
    audio_url: Optional[str] = None,
    audio: AudioMode = "auto",
    max_embed_mb: float = 25.0,
    title: Optional[str] = None,
    theme: Literal["dark", "light"] = "dark",
    width: int = 1600,
    height: int = 300,
    image_format: Literal["png", "webp", "jpeg"] = "png",
    **options,
) -> str:
    """Build a self-contained interactive player page and return its HTML.

    Args:
        source: Audio file path, or a numpy array (with ``sample_rate=``).
        output: Where to write the ``.html`` file (optional; HTML is returned either way).
        audio_url: Reference the audio at this URL instead of embedding it,
            for large files you host yourself. With ``start=``, the player
            seeks within that file.
        audio: How embedded audio is stored. ``"auto"`` keeps the original
            file if browsers can play it and it's under ``max_embed_mb``,
            otherwise it compresses to MP3 (needs ffmpeg) or falls back to
            WAV. ``"original"``, ``"m4a"``, ``"mp3"`` and ``"wav"`` force a choice.
        title: Heading shown above the player (default: the file name).
        theme: ``"dark"`` or ``"light"``.
        width, height: Spectrogram image size in pixels. The player stretches
            to the page width; ``height`` is also the on-screen height.
        image_format: Embedded image format. ``"webp"`` is smaller.
        **options: Any :func:`specrender.compute` or ``to_image`` option
            (``palette``, ``scale``, ``fmin``, ``fmax``, ``start``, ``end``,
            ``channel``, ``n_fft``, ``dynamic_range``, ...).
    """
    cfg, img_bytes, img_mime, audio_bytes, audio_mime = _build(
        source, audio_url=audio_url, audio=audio, max_embed_mb=max_embed_mb, title=title,
        theme=theme, width=width, height=height, image_format=image_format, options=options,
    )
    cfg["image"] = _data_uri(img_bytes, img_mime)
    if audio_bytes is not None:
        cfg["audio"] = _data_uri(audio_bytes, audio_mime)
    page = _page(cfg, theme)
    if output is not None:
        out = Path(output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page, encoding="utf-8")
    return page


def export_player(
    source: Source,
    out_dir: PathLike,
    *,
    name: Optional[str] = None,
    audio_url: Optional[str] = None,
    audio: AudioMode = "auto",
    max_embed_mb: float = float("inf"),
    title: Optional[str] = None,
    theme: Literal["dark", "light"] = "dark",
    width: int = 1600,
    height: int = 300,
    image_format: Literal["png", "webp", "jpeg"] = "png",
    **options,
) -> dict:
    """Write player files for embedding in your own pages.

    Creates in ``out_dir``: ``specrender-player.js`` (shared by all players),
    ``<name>.<image_format>``, ``<name>.json`` and the audio file (unless
    ``audio_url`` is given), plus ``<name>.html`` as a minimal example page.

    Returns a dict of the written paths and an ``"embed"`` HTML snippet.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stem = name or (Path(source).stem if not isinstance(source, np.ndarray) else "audio")
    cfg, img_bytes, img_mime, audio_bytes, audio_mime = _build(
        source, audio_url=audio_url, audio=audio, max_embed_mb=max_embed_mb, title=title,
        theme=theme, width=width, height=height, image_format=image_format, options=options,
    )
    ext = {"image/png": "png", "image/webp": "webp", "image/jpeg": "jpg"}[img_mime]
    img_path = out / f"{stem}.{ext}"
    img_path.write_bytes(img_bytes)
    cfg["image"] = quote(img_path.name)
    written = {"image": img_path}

    if audio_bytes is not None:
        a_ext = _ext_for_mime(audio_mime, source)
        a_path = out / f"{stem}{a_ext}"
        src_path = None if isinstance(source, np.ndarray) else Path(source)
        if src_path is not None and _same_file(src_path, a_path):
            if audio_bytes != src_path.read_bytes():   # re-encoded/cropped: never overwrite the source
                a_path = out / f"{stem}.player{a_ext}"
                if _same_file(src_path, a_path):       # pathological, but never clobber the input
                    raise FileExistsError(f"Refusing to overwrite the source audio {src_path}")
                a_path.write_bytes(audio_bytes)
        else:
            a_path.write_bytes(audio_bytes)
        cfg["audio"] = quote(a_path.name)
        written["audio"] = a_path

    meta_path = out / f"{stem}.json"
    meta_path.write_text(json.dumps(cfg, indent=1), encoding="utf-8")
    js_path = out / "specrender-player.js"
    js_path.write_text(player_js(), encoding="utf-8")
    embed = f'<spectro-player meta="{html.escape(quote(meta_path.name))}"></spectro-player>'
    example = out / f"{stem}.html"
    example.write_text(_example_page(cfg.get("title") or stem, embed, theme), encoding="utf-8")
    written.update(meta=meta_path, script=js_path, example=example, embed=embed)
    return written


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #
def _build(source, *, audio_url, audio, max_embed_mb, title, theme, width, height, image_format, options):
    ckeys, ikeys = _compute_keys(), _image_keys()
    unknown = set(options) - ckeys - ikeys - {"sample_rate"}
    if unknown:
        raise TypeError(f"Unknown option(s): {', '.join(sorted(unknown))}")
    if options.get("annotate"):
        raise ValueError("The player draws its own axes; leave annotate off")

    ckw = {k: v for k, v in options.items() if k in ckeys}
    ikw = {k: v for k, v in options.items() if k in ikeys}
    ckw.update(width=width, height=height)
    start = float(ckw.get("start", 0.0) or 0.0)
    end = ckw.get("end")

    spec: Spectrogram = compute(source, **ckw)
    img = spec.to_image(**ikw)
    buf = io.BytesIO()
    fmt = {"png": "PNG", "webp": "WEBP", "jpeg": "JPEG", "jpg": "JPEG"}[image_format]
    img.save(buf, format=fmt, **({"quality": 90} if fmt != "PNG" else {"optimize": True}))
    img_mime = {"PNG": "image/png", "WEBP": "image/webp", "JPEG": "image/jpeg"}[fmt]

    if title is None and not isinstance(source, np.ndarray):
        title = Path(source).name

    lo, hi = spec.level_bounds(ikw.get("dynamic_range", 80.0), ikw.get("db_range"))
    bands = _bands(spec.channels, int(height), int(ckw.get("channel_gap", 2)))
    cfg = {
        "version": 1,
        "title": title or "",
        "duration": float(spec.duration),
        "time_offset": start,
        "audio_offset": 0.0,
        "scale": spec.scale,
        "fmin": float(spec.fmin),
        "fmax": float(spec.fmax),
        "height": int(height),
        "channels": bands,
        "yticks": _freq_ticks(spec.fmin, spec.fmax, spec.scale, bands[0]["height"] * int(height)),
        "db_range": [round(lo, 1), round(hi, 1)],
        "sample_rate": int(spec.sample_rate),
        "theme": theme,
    }

    if audio_url:
        cfg["audio"] = audio_url
        cfg["audio_offset"] = start
        return cfg, buf.getvalue(), img_mime, None, None

    audio_bytes, audio_mime = _audio_payload(
        source, options.get("sample_rate"), start, end, audio, max_embed_mb)
    cfg["audio_type"] = audio_mime
    return cfg, buf.getvalue(), img_mime, audio_bytes, audio_mime


def _bands(channels: int, height: int, gap: int) -> list[dict]:
    """Fractional vertical extent of each stacked channel, matching core._split_height."""
    from .core import _split_height

    per, gaps = _split_height(height, channels, gap)
    bands, y = [], 0
    for c in range(channels):
        bands.append({"top": y / height, "height": per[c] / height})
        y += per[c] + (gaps[c] if c < len(gaps) else 0)
    return bands


def _freq_ticks(fmin: float, fmax: float, scale: str, band_px: float) -> list[dict]:
    """Frequency labels for one channel band, at least MIN_GAP_PX apart on screen."""
    lo, hi = _to_scale(fmin, scale), _to_scale(fmax, scale)
    out = []
    for t in freq_ticks(fmin, fmax, scale, band_px, label_px=LABEL_PX):
        pos = float((_to_scale(t, scale) - lo) / (hi - lo))
        out.append({"hz": float(t), "label": _fmt_hz(float(t)) if t else "0", "pos": round(pos, 5)})
    return out


def _audio_payload(source, sample_rate, start, end, mode, max_mb) -> tuple[bytes, str]:
    is_path = not isinstance(source, np.ndarray)
    cropped = bool(start) or end is not None
    path = Path(source) if is_path else None
    ext = path.suffix.lower() if path else ""
    has_ffmpeg = shutil.which("ffmpeg") is not None

    if mode in ("auto", "original") and is_path and not cropped and not sample_rate and ext in BROWSER_AUDIO:
        size_mb = path.stat().st_size / 1e6
        if mode == "original" or size_mb <= max_mb or not has_ffmpeg:
            if size_mb > max_mb:
                warnings.warn(f"Embedding {size_mb:.0f} MB of audio; install ffmpeg to compress it, "
                              "or use audio_url=", stacklevel=3)
            return path.read_bytes(), BROWSER_AUDIO[ext]

    if mode == "original":
        if not is_path or ext not in BROWSER_AUDIO:
            raise ValueError(f"Browsers can't play {ext or 'array'} audio; use audio='auto'")
        if cropped:
            raise ValueError("audio='original' can't be combined with start/end")

    # Decode (and crop) to samples, then encode
    if is_path:
        x, sr = load_audio(path, start=start, end=end, sample_rate=sample_rate)
    else:
        x = np.asarray(source, dtype=np.float32)
        x = x[None, :] if x.ndim == 1 else (x.T if x.shape[0] > x.shape[1] else x)
        sr = int(sample_rate)
        a = int(round(start * sr))
        b = None if end is None else int(round(end * sr))
        x = x[:, a:b]

    # MP3 plays in every browser (AAC/M4A doesn't in some open-source builds)
    want = mode if mode in ("m4a", "mp3", "wav") else ("mp3" if has_ffmpeg else "wav")
    if want in ("m4a", "mp3") and not has_ffmpeg:
        raise RuntimeError(f"audio='{want}' needs ffmpeg on PATH")
    if want == "wav":
        return _encode_wav(x, sr), "audio/wav"
    return _encode_ffmpeg(x, sr, want), ("audio/mp4" if want == "m4a" else "audio/mpeg")


def _encode_wav(x: np.ndarray, sr: int) -> bytes:
    from scipy.io import wavfile

    pcm = (np.clip(x, -1.0, 1.0) * 32767.0).astype("<i2").T
    buf = io.BytesIO()
    wavfile.write(buf, int(sr), pcm)
    return buf.getvalue()


def _encode_ffmpeg(x: np.ndarray, sr: int, kind: str) -> bytes:
    C = x.shape[0]
    codec = ["-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart"] if kind == "m4a" \
        else ["-c:a", "libmp3lame", "-b:a", "192k"]
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / f"a.{kind}"
        cmd = ["ffmpeg", "-nostdin", "-v", "error", "-f", "f32le", "-ar", str(sr), "-ac", str(C),
               "-i", "-", *codec, str(out)]
        proc = subprocess.run(cmd, input=np.ascontiguousarray(x.T, dtype="<f4").tobytes(),
                              capture_output=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError("ffmpeg failed: " + proc.stderr.decode(errors="replace").strip())
        return out.read_bytes()


def _same_file(a: Path, b: Path) -> bool:
    """True if both paths are the same file on disk. Unlike comparing resolved
    paths, this catches case-insensitive filesystems (macOS, Windows:
    ``Rec.WAV`` vs ``Rec.wav``) and hard links."""
    try:
        return os.path.samefile(a, b)
    except OSError:          # b doesn't exist yet
        return False


def _ext_for_mime(mime: str, source) -> str:
    if not isinstance(source, np.ndarray):
        ext = Path(source).suffix.lower()
        if BROWSER_AUDIO.get(ext) == mime:
            return ext
    return {"audio/mp4": ".m4a", "audio/mpeg": ".mp3", "audio/wav": ".wav"}.get(mime, ".bin")


def _data_uri(data: bytes, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(data).decode("ascii")


def _json_for_script(obj) -> str:
    # Safe to place inside <script>: no "</" sequences or U+2028/9 line breaks
    return (json.dumps(obj, separators=(",", ":"))
            .replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def _page(cfg: dict, theme: str) -> str:
    title = html.escape(cfg.get("title") or "Spectrogram player")
    bg, fg = ("#0b0b0d", "#e4e4e7") if theme == "dark" else ("#f6f6f8", "#1d1d20")
    js = player_js().replace("</script", "<\\/script")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="generator" content="specrender">
<title>{title}</title>
<style>
  html,body{{margin:0;background:{bg};color:{fg}}}
  main{{max-width:1400px;margin:0 auto;padding:16px}}
  .help{{font:12px/1.5 system-ui,sans-serif;opacity:.7;margin:10px 4px 0}}
  kbd{{font:inherit;border:1px solid currentColor;border-radius:3px;padding:0 4px;opacity:.9}}
</style>
</head>
<body>
<main>
<spectro-player theme="{html.escape(theme)}"><script type="application/json">{_json_for_script(cfg)}</script></spectro-player>
<p class="help">Click to jump · drag the white line to scrub · drag across the spectrogram to select and loop ·
double-click or <kbd>Esc</kbd> clears · <kbd>Space</kbd> play/pause · <kbd>←</kbd>/<kbd>→</kbd> seek (<kbd>Shift</kbd> = 5 s) · <kbd>L</kbd> loop</p>
</main>
<script>
{js}
</script>
</body>
</html>
"""


def _example_page(title: str, embed: str, theme: str) -> str:
    bg = "#0b0b0d" if theme == "dark" else "#f6f6f8"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<script src="specrender-player.js" defer></script>
<style>html,body{{margin:0;background:{bg}}} main{{max-width:1400px;margin:0 auto;padding:16px}}</style>
</head>
<body>
<main>
{embed}
</main>
</body>
</html>
"""
