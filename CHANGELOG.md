# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-10-17

### Added
- `render()`, `compute()` and `render_batch()` for turning audio files or numpy arrays into spectrogram images.
- Exact `width` × `height` output, including stacked channels (`channel="all"`).
- Linear, log and mel frequency scales, with `fmin`/`fmax` and `start`/`end`.
- 11 built-in palettes that need no matplotlib, plus matplotlib colormaps, custom color lists and `register_palette()`.
- PNG, JPEG, WebP, BMP, TIFF and GIF output, and in-memory `to_bytes()`.
- dBFS levels with `dynamic_range`, fixed `db_range`, `gamma`, and `shared_levels` for batches.
- Streaming column pooling with `aggregate="max"|"mean"`, so long files render in bounded memory.
- Annotated output (axes, title, dB colorbar, dark or light theme) via matplotlib.
- Audio loading through scipy (WAV), soundfile (FLAC/OGG/AIFF) and ffmpeg (MP3/M4A/Opus/video).
- `specrender` command-line tool.

[0.1.0]: https://github.com/kk4cnm/specrender/releases/tag/v0.1.0
