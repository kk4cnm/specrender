# specrender

[![CI](https://github.com/kk4cnm/specrender/actions/workflows/ci.yml/badge.svg)](https://github.com/kk4cnm/specrender/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

**Render spectrogram images from audio files**, or **interactive HTML players**
that play the audio over its spectrogram. Images come out at exactly the
pixel size you ask for, in any palette, as PNG, JPG, WebP, BMP, TIFF or GIF.
Hour-long recordings render without loading the whole spectrogram into memory.

![Annotated stereo spectrogram](https://github.com/kk4cnm/specrender/raw/main/docs/images/annotated.png)

- **Exact output size.** `width` × `height` is what you get, including stereo channels stacked with a gap between them.
- **Any palette.** 11 built-in palettes that need no matplotlib, any matplotlib colormap name, or your own colors.
- **Linear, log or mel frequency axis**, with `fmin`/`fmax` limits and `start`/`end` time cropping.
- **Comparable levels.** Levels are measured in dBFS, so a fixed `db_range` puts many files on the same brightness scale.
- **Short events stay visible when you scale down.** Max-pooling keeps a 1 ms click in a 10-minute file on screen.
- **Most audio formats.** WAV needs nothing extra. FLAC, OGG and AIFF use `soundfile`. MP3, M4A, Opus and video files use `ffmpeg`. Numpy arrays also work as input.
- **Interactive player.** A single HTML file with play/pause, volume and speed controls. Click to jump, drag the playhead to scrub, and drag across the spectrogram to select a region and loop it.
- **Library and CLI.** Use `sr.render(...)` from Python, or run `specrender *.wav -d out/`.

## Install

```bash
pip install "specrender[all]"
```

The core install needs only numpy, scipy and Pillow. The extras add more:

| Extra | Adds | For |
|---|---|---|
| `annotate` | matplotlib | `annotate=True` (axes, labels, colorbar) and matplotlib colormap names |
| `formats` | soundfile | FLAC, OGG and AIFF without ffmpeg |
| `all` | both | |

For MP3, M4A and similar formats, install [ffmpeg](https://ffmpeg.org/download.html) and make sure it's on your `PATH`.

## Quick start

```python
import specrender as sr

# Load, analyse, render and save in one call
sr.render("recording.mp3", "recording.png", width=1200, height=400, palette="magma")

# Speech: mel scale up to 8 kHz, saved as JPEG
sr.render("voice.wav", "voice.jpg", width=800, height=300,
          scale="mel", fmax=8000, palette="viridis", quality=90)

# Labeled axes, title and dB colorbar
sr.render("chirp.flac", "chirp.png", width=1200, height=600,
          scale="log", annotate=True, title="Test chirp")
```

Compute once, then render as many ways as you like:

```python
spec = sr.compute("track.wav", scale="log", width=1600, height=500)

spec.save("dark.png",  palette="inferno")
spec.save("print.jpg", palette="gray_r", dynamic_range=60)
png = spec.to_bytes("PNG", palette="waterfall")   # bytes, e.g. for a web response
img = spec.to_image(palette="cividis")            # a PIL.Image you can compose further

spec.db      # (channels, rows, cols) in dBFS; row 0 is the lowest frequency
spec.freqs   # Hz at each row
spec.times   # seconds at each column
```

Numpy arrays from an SDR, a microphone or generated signals work too:

```python
sr.render(samples, "iq_audio.png", sample_rate=48000, width=1000, height=300)
```

To render a folder of clips on a shared brightness scale:

```python
from pathlib import Path
sr.render_batch(sorted(Path("clips").glob("*.wav")), "out/", format="webp",
                width=600, height=200, shared_levels=True)
```

## Interactive player

![Interactive spectrogram player](https://github.com/kk4cnm/specrender/raw/main/docs/images/player.png)

```python
sr.player("recording.mp3", "recording.html", scale="mel", fmax=8000, palette="magma")
```

```bash
specrender recording.mp3 -o recording.html
```

This writes **one self-contained HTML file**, with the spectrogram, the audio
and the player script all inside it. Open it in any browser; no server or
internet connection is needed.

| Do this | To |
|---|---|
| Click | Jump to that point |
| Drag the white playhead | Scrub |
| Drag across the spectrogram | Select a region. Playback loops inside it |
| Drag a selection edge | Resize the selection |
| Double-click or <kbd>Esc</kbd> | Clear the selection |
| <kbd>Space</kbd> · <kbd>←</kbd>/<kbd>→</kbd> (<kbd>Shift</kbd> = 5 s) · <kbd>L</kbd> | Play/pause · seek · toggle loop |

Hover over the spectrogram to read the time and frequency under the cursor.
There are also a volume slider, a mute button and a playback-speed menu.

**On your own website**, write separate files and use the `<spectro-player>` tag:

```python
sr.export_player("talk.mp3", "site/players/")   # specrender-player.js, talk.png, talk.json, talk.mp3
```

```html
<script src="players/specrender-player.js" defer></script>
<spectro-player meta="players/talk.json"></spectro-player>
```

Large files can stay where they're hosted: pass `audio_url="https://…/talk.mp3"`
and only the image and settings are generated. Try
[`docs/player-demo.html`](https://github.com/kk4cnm/specrender/raw/main/docs/player-demo.html)
(download it, then open it), or see the
[player guide](https://github.com/kk4cnm/specrender/blob/main/docs/guide.md#interactive-html-player).

## Command line

```bash
specrender talk.mp3 -o talk.png -W 1600 -H 500 -p inferno -s mel --fmax 8000
specrender *.wav -d thumbs/ -f webp -W 400 -H 120 --db-range -90:0
specrender capture.flac -o annotated.png -a --title "{name}" -s log
specrender session.flac -o session.html -s log      # interactive player
specrender --list-palettes
```

## Palettes

![Built-in palettes](https://github.com/kk4cnm/specrender/raw/main/docs/images/palettes.png)

Add `_r` to any palette name to reverse it (`"gray_r"` gives dark-on-light for print).
To register your own palette:

```python
sr.register_palette("brand", ["#0b0b2b", "#3355ff", "#ffffff"])
```

## Documentation

- **[User guide](https://github.com/kk4cnm/specrender/blob/main/docs/guide.md):** choosing FFT size, frequency scales, dynamic range, channels, long files, and recipes for speech, music and radio.
- **[API reference](https://github.com/kk4cnm/specrender/blob/main/docs/api.md):** every function, method and parameter.
- **[CLI reference](https://github.com/kk4cnm/specrender/blob/main/docs/cli.md):** every flag, with examples.
- **[Changelog](https://github.com/kk4cnm/specrender/blob/main/CHANGELOG.md)**

## Development

```bash
git clone https://github.com/kk4cnm/specrender && cd specrender
pip install -e ".[dev]"
pytest
python examples/make_gallery.py   # regenerates docs/images/
```

See [CONTRIBUTING.md](https://github.com/kk4cnm/specrender/blob/main/CONTRIBUTING.md) for details.

## License

MIT. See [LICENSE](https://github.com/kk4cnm/specrender/blob/main/LICENSE).
