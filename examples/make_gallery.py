"""Regenerate the images in docs/images/ from synthetic test signals.

    python examples/make_gallery.py

No audio files needed: the signals are generated here, so the gallery is
reproducible on any machine.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.signal import chirp

import specrender as sr

OUT = Path(__file__).resolve().parent.parent / "docs" / "images"
FS = 22050


def demo_signal(seconds: float = 6.0) -> np.ndarray:
    """Stereo: left = log chirp + steady 1 kHz tone; right = gated 440 Hz + noise."""
    rng = np.random.default_rng(7)
    t = np.arange(int(seconds * FS)) / FS
    left = 0.5 * chirp(t, 100, seconds, 9000, method="logarithmic") + 0.2 * np.sin(2 * np.pi * 1000 * t)
    gate = np.sin(2 * np.pi * 2 * t) > 0
    right = 0.3 * np.sin(2 * np.pi * 440 * t) * gate + 0.02 * rng.standard_normal(len(t))
    return np.stack([left, right]).astype(np.float32)


def speechlike(seconds: float = 4.0) -> np.ndarray:
    """Harmonic stack with a wandering pitch and moving formants, gated into syllables."""
    t = np.arange(int(seconds * FS)) / FS
    f0 = 140 + 30 * np.sin(2 * np.pi * 0.7 * t)
    phase = 2 * np.pi * np.cumsum(f0) / FS
    x = np.zeros_like(t)
    for h in range(1, 30):
        fh = h * f0
        formant = np.exp(-((fh - (700 + 300 * np.sin(2 * np.pi * 1.3 * t))) / 250) ** 2) \
            + 0.6 * np.exp(-((fh - (1800 + 500 * np.cos(2 * np.pi * 0.9 * t))) / 350) ** 2)
        x += formant * np.sin(h * phase) / h ** 0.3
    env = (np.sin(2 * np.pi * 2.5 * t) > -0.3).astype(float)
    return (0.3 * x * np.convolve(env, np.ones(400) / 400, "same")).astype(np.float32)


def label(img: Image.Image, text: str) -> Image.Image:
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, 8 + 7 * len(text), 20), fill=(0, 0, 0))
    d.text((5, 4), text, fill=(255, 255, 255))
    return img


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    x = demo_signal()

    # Hero: annotated stereo
    sr.render(x, OUT / "annotated.png", sample_rate=FS, channel="all", scale="log",
              width=1000, height=500, annotate=True, title="Log chirp + 1 kHz tone / gated 440 Hz + noise")

    # Palettes: one spectrogram, every built-in palette
    spec = sr.compute(x, sample_rate=FS, scale="log", width=480, height=90)
    names = sr.list_palettes()
    names = [n for n in names if n != "grey"]
    tiles = [label(spec.to_image(palette=n, width=480, height=90, dynamic_range=70), n) for n in names]
    cols = 2
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * 480 + (cols - 1) * 4, rows * 90 + (rows - 1) * 4), (24, 24, 24))
    for i, tile in enumerate(tiles):
        sheet.paste(tile, ((i % cols) * 484, (i // cols) * 94))
    sheet.save(OUT / "palettes.png", optimize=True)

    # Scales: linear vs log vs mel on speech-like audio
    s = speechlike()
    scale_tiles = [label(sr.render(s, sample_rate=FS, scale=sc, fmax=8000, width=480, height=160,
                                   palette="inferno"), sc) for sc in ("linear", "log", "mel")]
    sheet = Image.new("RGB", (480, 3 * 160 + 8), (24, 24, 24))
    for i, tile in enumerate(scale_tiles):
        sheet.paste(tile, (0, i * 164))
    sheet.save(OUT / "scales.png", optimize=True)

    # Aggregate: 1 ms clicks in 10 minutes of noise, pooled to 600 px, same dB scale for both
    rng = np.random.default_rng(1)
    long = (0.003 * rng.standard_normal(FS * 600)).astype(np.float32)
    for k in (0.25, 0.5, 0.75):
        i = int(k * len(long))
        long[i:i + 22] += 0.8
    agg = [label(sr.render(long, sample_rate=FS, aggregate=a, width=600, height=120, palette="magma", db_range=(-90, -25)),
                 f"aggregate={a}") for a in ("max", "mean")]
    sheet = Image.new("RGB", (600, 244), (24, 24, 24))
    for i, tile in enumerate(agg):
        sheet.paste(tile, (0, i * 124))
    sheet.save(OUT / "aggregate.png", optimize=True)

    print("wrote", ", ".join(p.name for p in sorted(OUT.glob("*.png"))))


if __name__ == "__main__":
    main()
