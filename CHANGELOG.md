# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [0.2.0] - 2026-10-18

### Added
- Interactive HTML player: `sr.player()` writes one self-contained page with the spectrogram and audio. Click to jump, drag the playhead to scrub, drag to select a region and loop it, resize the selection by its edges, and use the play/pause, volume, mute and speed controls, keyboard shortcuts, and the time and frequency readout on hover.
- `sr.export_player()` and the `<spectro-player>` web component for embedding players in your own pages, with a JavaScript API (`play`, `pause`, `currentTime`, `selection`, `loop`) and `spectro-selection`/`spectro-time` events.
- CLI: `-o file.html` / `-f html` writes a player. New `--audio`, `--audio-url` and `--web` options.
- Browser end-to-end test (`tests/browser_check.py`), run in CI.

### Fixed
- Frequency labels no longer overlap. On mel scale at small heights, the 20, 50 and 100 Hz labels were drawn a few pixels apart. Ticks are now picked by importance and kept at least 16 px apart, in both the player and annotated images.
- `export_player` can no longer overwrite the source audio when the exported file name refers to the same file under another spelling (case-insensitive filesystems on macOS and Windows, or hard links).
- The playhead stays draggable where it overlaps a selection edge: its top handle scrubs, and the rest of the edge resizes. The handle area is capped at 35% of the player height, so short players keep a resize area.

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

[0.2.0]: https://github.com/kk4cnm/specrender/releases/tag/v0.2.0
[0.1.0]: https://github.com/kk4cnm/specrender/releases/tag/v0.1.0
