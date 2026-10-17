"""specrender: render spectrogram images from audio files.

Quick start::

    import specrender as sr
    sr.render("speech.mp3", "speech.png", width=1200, height=400,
              palette="magma", scale="mel", fmax=8000)
"""
from .audio import AudioLoadError, load_audio
from .core import Spectrogram, compute, render, render_batch, save_image
from .palettes import get_palette, list_palettes, register_palette

__all__ = [
    "AudioLoadError", "Spectrogram", "compute", "get_palette", "list_palettes",
    "load_audio", "register_palette", "render", "render_batch", "save_image",
]
__version__ = "0.1.0"
