# API reference

```python
import specrender as sr
```

| Name | What it does |
|---|---|
| [`render()`](#render) | Compute, render and (optionally) save in one call |
| [`compute()`](#compute) | Analyse audio and return a `Spectrogram` |
| [`Spectrogram`](#spectrogram) | The result; render it with `to_image()`, `save()` or `to_bytes()` |
| [`render_batch()`](#render_batch) | Render many files into a folder |
| [`save_image()`](#save_image) | Save a PIL image, picking the format from the extension |
| [`load_audio()`](#load_audio) | Decode an audio file to a float32 array |
| [`player()`](#player) | Write a self-contained interactive HTML player |
| [`export_player()`](#export_player) | Write player files for embedding in your own pages |
| [`get_palette()`](#get_palette), [`list_palettes()`](#list_palettes), [`register_palette()`](#register_palette) | Palettes |
| `AudioLoadError` | Raised when no loader can decode a file |

---

## `render`

```python
sr.render(source, output=None, *, format=None, quality=92, **options) -> PIL.Image.Image
```

Computes a spectrogram, renders it, and saves it to `output` if you give one.
It always returns the image.

- **source**: a path, a numpy array (requires `sample_rate=`), or an existing `Spectrogram`.
- **output**: file path. The format comes from the extension unless you set `format`.
- **format**: `"png"`, `"jpg"`/`"jpeg"`, `"webp"`, `"bmp"`, `"tiff"` or `"gif"`.
- **quality**: JPEG and WebP quality, 1–100.
- **\*\*options**: any keyword of [`compute()`](#compute) or [`Spectrogram.to_image()`](#to_image).
  Unknown keywords raise `TypeError`, so a typo fails loudly instead of being ignored.

---

## `compute`

```python
sr.compute(source, *, sample_rate=None, channel="mix", start=0.0, end=None,
           n_fft=2048, hop_length=None, window="hann", scale="linear",
           fmin=None, fmax=None, width=None, height=None, channel_gap=2,
           aggregate="max", pre_emphasis=0.0) -> Spectrogram
```

| Parameter | Default | Description |
|---|---|---|
| `source` | — | Path to an audio file, or an array shaped `(n,)`, `(channels, n)` or `(n, channels)` |
| `sample_rate` | `None` | Resample a file to this rate. Required for array input |
| `channel` | `"mix"` | `"mix"`, `"left"`, `"right"`, `"side"`, an int index, or `"all"` (stack every channel) |
| `start`, `end` | `0`, `None` | Time window in seconds |
| `n_fft` | `2048` | FFT size in samples (≥ 16) |
| `hop_length` | `n_fft // 4` | Samples between frames |
| `window` | `"hann"` | Any `scipy.signal.get_window` spec, e.g. `("kaiser", 12)` |
| `scale` | `"linear"` | `"linear"`, `"log"` or `"mel"` |
| `fmin` | `0`, or `max(20, sr/n_fft)` for log and mel | Lowest frequency in Hz |
| `fmax` | Nyquist | Highest frequency in Hz (capped at Nyquist) |
| `width` | native | Columns. Long inputs are pooled to this while streaming |
| `height` | native | Total rows, including channel gaps |
| `channel_gap` | `2` | Pixels between stacked channels (used to split `height`) |
| `aggregate` | `"max"` | `"max"` or `"mean"`: how frames and bins are combined when downscaling |
| `pre_emphasis` | `0.0` | First-order high-pass coefficient (e.g. `0.97` for speech) |

Raises `FileNotFoundError`, `AudioLoadError` or `ValueError` (bad ranges, unknown channel, empty selection).

---

## `Spectrogram`

A dataclass returned by `compute()`.

| Attribute | Type | Description |
|---|---|---|
| `db` | `ndarray (channels, rows, cols)` float32 | Level in dBFS. Row 0 is the lowest frequency |
| `freqs` | `ndarray (rows,)` | Center frequency of each row, in Hz |
| `times` | `ndarray (cols,)` | Center time of each column, in seconds from the start of the file |
| `sample_rate` | `int` | Sample rate that was analysed |
| `scale` | `str` | `"linear"`, `"log"` or `"mel"` |
| `fmin`, `fmax` | `float` | Frequency range covered |
| `duration` | `float` | Seconds analysed |
| `start` | `float` | Offset of the analysed window in the file |
| `channels` | `int` (property) | Number of stacked channels |
| `params` | `dict` | Analysis settings (`n_fft`, `hop_length`, `window`, `channel`, `aggregate`, `width`, `height`, `channel_gap`) |

### `to_image`

```python
spec.to_image(*, width=None, height=None, palette="magma", dynamic_range=80.0,
              db_range=None, gamma=1.0, channel_gap=2, gap_color="#000000",
              annotate=False, title=None, colorbar=True, theme="dark", dpi=100)
    -> PIL.Image.Image  # RGB
```

| Parameter | Default | Description |
|---|---|---|
| `width`, `height` | size given to `compute()`, else native | Exact output size in pixels |
| `palette` | `"magma"` | Name, `"name_r"`, list of colors, or an `(N, 3)` array. See [`get_palette`](#get_palette) |
| `dynamic_range` | `80.0` | dB shown below the loudest point |
| `db_range` | `None` | Fixed `(low, high)` in dBFS. Overrides `dynamic_range` |
| `gamma` | `1.0` | Values > 1 brighten quiet detail |
| `channel_gap`, `gap_color` | `2`, `"#000000"` | Spacing and color between stacked channels |
| `annotate` | `False` | Add axes, labels and a colorbar (requires matplotlib). The whole figure is `width` × `height` (default 1200×600) |
| `title` | `None` | Figure title (only with `annotate`) |
| `colorbar` | `True` | dB colorbar (only with `annotate`) |
| `theme` | `"dark"` | `"dark"` or `"light"` (only with `annotate`) |
| `dpi` | `100` | Font scale for `annotate`. Output pixels don't change |

### `save`

```python
spec.save(path, *, format=None, quality=92, **to_image_options) -> pathlib.Path
```

### `to_bytes`

```python
spec.to_bytes(format="PNG", *, quality=92, **to_image_options) -> bytes
```

### `levels`, `level_bounds`

```python
spec.levels(dynamic_range=80.0, db_range=None, gamma=1.0) -> ndarray  # 0..1, same shape as db
spec.level_bounds(dynamic_range=80.0, db_range=None) -> (low_db, high_db)
```

Use these to feed the normalized data into your own plotting or ML pipeline.

---

## `render_batch`

```python
sr.render_batch(sources, out_dir, *, format="png", quality=92,
                shared_levels=False, dynamic_range=80.0, **options) -> list[pathlib.Path]
```

Writes `<out_dir>/<stem>.<format>` for each source. With `shared_levels=True`,
every image uses the same dB scale, topped by the loudest point across all the
files. This computes every spectrogram first, so memory grows with the number of files.

---

## `save_image`

```python
sr.save_image(img, path, *, format=None, quality=92) -> pathlib.Path
```

Creates parent folders as needed. JPEG is written without chroma subsampling
and PNG with `optimize=True`.

---

## `load_audio`

```python
sr.load_audio(path, *, start=0.0, end=None, sample_rate=None) -> (ndarray, int)
```

Returns float32 samples in [-1, 1] shaped `(channels, n)`, plus the sample
rate. It tries scipy (WAV), then `soundfile`, then `ffmpeg`. If all fail, it
raises `AudioLoadError` with each loader's message.

---

## `player`

```python
sr.player(source, output=None, *, audio_url=None, audio="auto", max_embed_mb=25.0,
          title=None, theme="dark", width=1600, height=300, image_format="png",
          **options) -> str
```

Builds a single HTML page containing the spectrogram, the audio and the
`<spectro-player>` script, writes it to `output` if you give one, and returns the HTML.

| Parameter | Default | Description |
|---|---|---|
| `source` | — | File path, or array with `sample_rate=` |
| `audio_url` | `None` | Play this URL instead of embedding audio. With `start=`, the player seeks within it |
| `audio` | `"auto"` | `"auto"`, `"original"`, `"mp3"`, `"m4a"` or `"wav"` (see the [guide](guide.md#how-the-audio-gets-into-the-page)) |
| `max_embed_mb` | `25` | With `"auto"`, larger browser-playable files are compressed to MP3 |
| `title` | file name | Shown above the player |
| `theme` | `"dark"` | `"dark"` or `"light"` |
| `width`, `height` | `1600`, `300` | Spectrogram image pixels. `height` is also the on-screen height |
| `image_format` | `"png"` | `"png"`, `"webp"` or `"jpeg"` |
| `**options` | | Any `compute()` / `to_image()` option except `annotate` |

## `export_player`

```python
sr.export_player(source, out_dir, *, name=None, audio_url=None, audio="auto",
                 title=None, theme="dark", width=1600, height=300,
                 image_format="png", **options) -> dict
```

Writes `specrender-player.js`, `<name>.<image_format>`, `<name>.json`, the
audio (unless `audio_url` is given) and an example `<name>.html` into `out_dir`.
Returns `{"image", "meta", "script", "example", "audio"?: Path, "embed": str}`.
Unlike `player()`, audio is never compressed by size here; pass `audio="mp3"` to force it.

## `player_js`

```python
sr.player_js() -> str
```

The `<spectro-player>` web component source, for bundling it yourself.

---

## `get_palette`

```python
sr.get_palette(palette) -> ndarray  # (256, 3) uint8
```

Accepts any of these:
- a name: a built-in, a registered palette, or a matplotlib colormap. Add `_r` to reverse it.
- a list of colors: `"#rgb"`/`"#rrggbb"` strings, or RGB tuples in 0–1 or 0–255.
- an `(N, 3)` array in 0–1 or 0–255.

## `list_palettes`

```python
sr.list_palettes(include_matplotlib=False) -> list[str]
```

## `register_palette`

```python
sr.register_palette(name, colors) -> None
```

Registers `name` for this process. Registered names take priority over built-ins.
