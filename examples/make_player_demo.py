"""Build docs/player-demo.html: an interactive player on a synthetic test signal.

    python examples/make_player_demo.py

The 12-second clip contains a Morse "CQ TEST" at 700 Hz, a speech-like harmonic
voice, a rising chirp and a few clicks, so there's something to find, select
and loop. Also saves docs/images/player.png (a screenshot) if Playwright is installed.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

import specrender as sr

FS = 22050
ROOT = Path(__file__).resolve().parent.parent
MORSE = {"C": "-.-.", "Q": "--.-", "T": "-", "E": ".", "S": "..."}


def morse(text: str, wpm: float = 18, freq: float = 700.0) -> np.ndarray:
    unit = 1.2 / wpm
    env = []
    for word in text.split():
        for ch in word:
            for sym in MORSE[ch]:
                env += [1] * (1 if sym == "." else 3) + [0]
            env += [0, 0]
        env += [0] * 4
    n_unit = int(unit * FS)
    gate = np.repeat(np.array(env, dtype=float), n_unit)
    ramp = np.hanning(int(0.01 * FS))
    gate = np.convolve(gate, ramp / ramp.sum(), "same")       # soft keying, no clicks
    t = np.arange(len(gate)) / FS
    return 0.35 * gate * np.sin(2 * np.pi * freq * t)


def voice(seconds: float) -> np.ndarray:
    t = np.arange(int(seconds * FS)) / FS
    f0 = 130 + 25 * np.sin(2 * np.pi * 0.6 * t)
    phase = 2 * np.pi * np.cumsum(f0) / FS
    x = np.zeros_like(t)
    for h in range(1, 35):
        fh = h * f0
        formants = (np.exp(-((fh - (650 + 250 * np.sin(2 * np.pi * 1.1 * t))) / 220) ** 2)
                    + 0.6 * np.exp(-((fh - (1700 + 450 * np.cos(2 * np.pi * 0.8 * t))) / 320) ** 2)
                    + 0.25 * np.exp(-((fh - 2800) / 400) ** 2))
        x += formants * np.sin(h * phase) / h ** 0.3
    syll = np.convolve((np.sin(2 * np.pi * 2.2 * t) > -0.2).astype(float), np.ones(300) / 300, "same")
    return 0.22 * x * syll


def build() -> np.ndarray:
    total = 12.0
    n = int(total * FS)
    rng = np.random.default_rng(3)
    x = 0.004 * rng.standard_normal(n)
    cw = morse("CQ TEST")
    x[int(0.3 * FS):int(0.3 * FS) + len(cw)] += cw[: n - int(0.3 * FS)]
    v = voice(4.0)
    i = int(6.2 * FS)
    x[i:i + len(v)] += v
    t = np.arange(int(2.0 * FS)) / FS
    sweep = 0.25 * np.sin(2 * np.pi * (300 * t + (6000 - 300) / (2 * 2.0) * t ** 2))
    i = int(3.8 * FS)
    x[i:i + len(sweep)] += sweep * np.hanning(len(sweep)) ** 0.2
    for c in (10.6, 10.9, 11.2):
        i = int(c * FS)
        x[i:i + 30] += 0.7
    return x.astype(np.float32)


def main() -> None:
    x = build()
    out = ROOT / "docs" / "player-demo.html"
    sr.player(x, out, sample_rate=FS, title="specrender player demo: Morse, chirp, voice, clicks",
              fmax=7000, palette="magma", width=1600, height=320, audio="mp3",
              n_fft=1024, dynamic_range=70)
    print("wrote", out, f"({out.stat().st_size / 1e6:.2f} MB)")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        p = b.new_page(viewport={"width": 1200, "height": 560}, device_scale_factor=1)
        p.goto(out.as_uri())
        P = "document.querySelector('spectro-player')"
        p.wait_for_function(f"{P}.duration > 0 && {P}.shadowRoot.querySelector('img').naturalWidth > 0")
        p.evaluate(f"{P}.selection = {{start: 6.3, end: 8.1}}; {P}.currentTime = 7.25")
        r = p.evaluate(f"(() => {{ const r = {P}.getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; }})()")
        p.screenshot(path=str(ROOT / "docs" / "images" / "player.png"),
                     clip={"x": r[0], "y": r[1], "width": r[2], "height": r[3]})
        b.close()
    print("wrote docs/images/player.png")


if __name__ == "__main__":
    main()
