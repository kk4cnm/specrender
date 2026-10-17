# CLI reference

```
specrender [options] INPUT [INPUT ...]
```

Installing the package adds the `specrender` command. Each input file is
rendered to one image. If any file fails, the others are still rendered, and
the command exits with status 1.

## Output

| Flag | Default | Description |
|---|---|---|
| `-o, --output FILE` | — | Output file. Only works with a single input |
| `-d, --out-dir DIR` | next to the input | Folder for `<stem>.<format>` outputs |
| `-f, --format FMT` | from `-o`, else `png` | `png`, `jpg`, `webp`, `bmp`, `tiff`, `gif`, or `html` for an interactive player |
| `-q, --quality N` | `92` | JPEG/WebP quality |

## Size and look

| Flag | Default | Description |
|---|---|---|
| `-W, --width PX` | `1200` | Output width |
| `-H, --height PX` | `400` | Output height |
| `-p, --palette NAME` | `magma` | Palette name (`_r` reverses it), or comma-separated hex colors: `-p "#000,#0f0,#fff"` |
| `-r, --dynamic-range DB` | `80` | dB shown below the loudest point |
| `--db-range LOW:HIGH` | — | Fixed dBFS scale, e.g. `--db-range -90:0` |
| `--gamma G` | `1.0` | Values > 1 brighten quiet detail |
| `-a, --annotate` | off | Axes, labels and colorbar (requires matplotlib) |
| `--title TEXT` | — | Title for `--annotate`. `{name}` is replaced with the input file name |
| `--light` | off | Light theme for `--annotate` |

## HTML player

These apply when the output is `.html` (`-o file.html` or `-f html`).

| Flag | Default | Description |
|---|---|---|
| `--audio MODE` | `auto` | `auto`, `original`, `mp3`, `m4a` or `wav`: how the audio is embedded |
| `--audio-url URL` | — | Link to hosted audio instead of embedding it |
| `--web` | off | Write separate files (`specrender-player.js`, image, JSON, audio, example page) for your own site, instead of one HTML file |

`-W`/`-H`, `-p`, `-s`, `--fmin`/`--fmax`, `--start`/`--end`, `--title` and
`--light` all apply to the player too.

## Analysis

| Flag | Default | Description |
|---|---|---|
| `-s, --scale` | `linear` | `linear`, `log` or `mel` |
| `--fmin HZ`, `--fmax HZ` | 0 (20 for log and mel), Nyquist | Frequency range |
| `--start S`, `--end S` | whole file | Time range in seconds |
| `-n, --n-fft N` | `2048` | FFT size |
| `--hop N` | `n_fft/4` | Hop length in samples |
| `--window NAME` | `hann` | Any scipy window name |
| `-c, --channel` | `mix` | `mix`, `left`, `right`, `side`, `all`, or an index |
| `--aggregate` | `max` | `max` or `mean` |
| `--pre-emphasis A` | `0` | e.g. `0.97` for speech |

## Other

| Flag | Description |
|---|---|
| `--list-palettes` | Print every palette name (including matplotlib's, if installed) and exit |
| `--version` | Print the version and exit |

## Examples

```bash
# One file, specific size and palette
specrender interview.mp3 -o interview.png -W 1600 -H 500 -p inferno

# Speech on mel scale up to 8 kHz
specrender talk.wav -o talk.webp -s mel --fmax 8000 -n 1024 --pre-emphasis 0.97

# A folder of clips → WebP thumbnails on a shared brightness scale
specrender clips/*.flac -d thumbs/ -f webp -W 400 -H 120 --db-range -90:0

# Stereo stacked, annotated with the file name as the title
specrender mix.wav -o mix.png -c all -a --title "{name}" -W 1400 -H 700

# Interactive player in one HTML file
specrender interview.mp3 -o interview.html -s mel --fmax 8000

# Player files for a website, audio served from your own URL
specrender talk.flac -f html --web -d site/players/ --audio-url https://example.com/audio/talk.mp3

# 30 seconds from minute 2, narrowband detail for radio audio
specrender rx.wav -o rx.png --start 120 --end 150 --fmax 3000 -n 8192 -p waterfall
```
