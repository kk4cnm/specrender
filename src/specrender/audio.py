"""Audio loading.

Backends, tried in order:
  * WAV via scipy (no extra dependencies)
  * Anything libsndfile reads (FLAC, OGG, AIFF, ...) via ``soundfile``, if installed
  * Anything else (MP3, M4A, Opus, video files, ...) via the ``ffmpeg`` CLI, if on PATH
"""
from __future__ import annotations

import json
import shutil
import subprocess
from math import gcd
from pathlib import Path
from typing import Optional, Union

import numpy as np

PathLike = Union[str, Path]


class AudioLoadError(RuntimeError):
    """Raised when no backend can decode a file."""


def load_audio(
    path: PathLike,
    *,
    start: float = 0.0,
    end: Optional[float] = None,
    sample_rate: Optional[int] = None,
) -> tuple[np.ndarray, int]:
    """Load audio as float32 in [-1, 1].

    Returns ``(samples, sr)`` where ``samples`` has shape ``(channels, n)``.
    ``start``/``end`` are in seconds; ``sample_rate`` resamples if given.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    if start < 0 or (end is not None and end <= start):
        raise ValueError("Need 0 <= start < end")

    errors: list[str] = []

    if path.suffix.lower() in (".wav", ".wave"):
        try:
            x, sr = _load_wav(path)
            x = _crop(x, sr, start, end)
            return _resample(x, sr, sample_rate)
        except Exception as e:  # e.g. WAV with compressed codec
            errors.append(f"scipy: {e}")

    try:
        import soundfile as sf
    except ImportError:
        sf = None
    if sf is not None:
        try:
            info = sf.info(str(path))
            sr = info.samplerate
            data, sr = sf.read(
                str(path),
                start=int(round(start * sr)),
                stop=None if end is None else int(round(end * sr)),
                dtype="float32",
                always_2d=True,
            )
            return _resample(data.T.copy(), sr, sample_rate)
        except Exception as e:
            errors.append(f"soundfile: {e}")

    if shutil.which("ffmpeg"):
        try:
            return _load_ffmpeg(path, start, end, sample_rate)
        except Exception as e:
            errors.append(f"ffmpeg: {e}")
    else:
        errors.append("ffmpeg: not found on PATH")

    raise AudioLoadError(f"Could not decode {path}:\n  " + "\n  ".join(errors))


def _load_wav(path: Path) -> tuple[np.ndarray, int]:
    import warnings

    from scipy.io import wavfile

    with warnings.catch_warnings():  # e.g. LIST/fact chunks scipy doesn't parse
        warnings.simplefilter("ignore", wavfile.WavFileWarning)
        sr, data = wavfile.read(str(path))
    if data.dtype == np.uint8:
        x = (data.astype(np.float32) - 128.0) / 128.0
    elif np.issubdtype(data.dtype, np.integer):
        x = data.astype(np.float32) / float(np.iinfo(data.dtype).max + 1)
    else:
        x = data.astype(np.float32)
    x = x.reshape(len(x), -1).T  # -> (channels, n)
    return np.ascontiguousarray(x), int(sr)


def _crop(x: np.ndarray, sr: int, start: float, end: Optional[float]) -> np.ndarray:
    a = int(round(start * sr))
    b = None if end is None else int(round(end * sr))
    return x[:, a:b]


def _resample(x: np.ndarray, sr: int, target: Optional[int]) -> tuple[np.ndarray, int]:
    if not target or target == sr:
        return x.astype(np.float32, copy=False), sr
    from scipy.signal import resample_poly

    g = gcd(int(sr), int(target))
    y = resample_poly(x, int(target) // g, int(sr) // g, axis=-1)
    return y.astype(np.float32), int(target)


def _load_ffmpeg(
    path: Path, start: float, end: Optional[float], sample_rate: Optional[int]
) -> tuple[np.ndarray, int]:
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=sample_rate,channels", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    streams = json.loads(probe.stdout).get("streams") or []
    if not streams:
        raise AudioLoadError("no audio stream")
    channels = int(streams[0]["channels"])
    sr = int(sample_rate or streams[0]["sample_rate"])

    cmd = ["ffmpeg", "-nostdin", "-v", "error"]
    if start:
        cmd += ["-ss", f"{start:.6f}"]
    cmd += ["-i", str(path)]
    if end is not None:
        cmd += ["-t", f"{end - start:.6f}"]
    cmd += ["-map", "0:a:0", "-f", "f32le", "-acodec", "pcm_f32le",
            "-ac", str(channels), "-ar", str(sr), "-"]
    proc = subprocess.run(cmd, capture_output=True, check=False)
    if proc.returncode != 0:
        raise AudioLoadError(proc.stderr.decode(errors="replace").strip())
    x = np.frombuffer(proc.stdout, dtype="<f4")
    x = x[: len(x) - len(x) % channels].reshape(-1, channels).T
    return np.ascontiguousarray(x), sr
