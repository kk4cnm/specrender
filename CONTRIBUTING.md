# Contributing

Bug reports, ideas and pull requests are welcome.

## Setup

```bash
git clone https://github.com/kk4cnm/specrender && cd specrender
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Install `ffmpeg` too if you want the MP3 test to run instead of being skipped.

## Before opening a pull request

- Run `pytest`, and make sure it passes.
- Add a test for any bug fix or new option. Tests generate their own signals with numpy, so please don't commit audio files.
- If you change something users can see, update `README.md`, the files in `docs/`, and `CHANGELOG.md` (under an "Unreleased" heading).
- If you change how images look, run `python examples/make_gallery.py` and commit the updated `docs/images/`.

## Design notes

- The core dependencies are numpy, scipy and Pillow only. matplotlib and soundfile stay optional, and should be imported inside the functions that use them.
- `compute()` holds the analysis settings and `Spectrogram.to_image()` holds the look settings. A new option belongs in one of the two, and `render()` routes keywords to the right one automatically.
- Output size must be exact. Every new rendering path should have a test that checks `img.size`.

## Releasing

1. Bump `version` in `pyproject.toml` and `__version__` in `src/specrender/__init__.py`.
2. Move the "Unreleased" entries in `CHANGELOG.md` under the new version.
3. Tag the release: `git tag vX.Y.Z && git push --tags`. The Release workflow builds the package and publishes it to PyPI. This needs the one-time trusted-publisher setup described at the top of `.github/workflows/release.yml`.
