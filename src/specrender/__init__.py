"""specrender: render spectrogram images from audio files.

Quick start::

    import specrender as sr
    sr.render("speech.mp3", "speech.png", width=1200, height=400,
              palette="magma", scale="mel", fmax=8000)
    sr.player("speech.mp3", "speech.html", scale="mel", fmax=8000)   # interactive
"""
from .audio import AudioLoadError, load_audio
from .core import Spectrogram, compute, render, render_batch, save_image
from .palettes import get_palette, list_palettes, register_palette
from .player import export_player, player, player_js

__all__ = [
    "AudioLoadError", "Spectrogram", "compute", "get_palette", "list_palettes",
    "export_player", "load_audio", "player", "player_js", "register_palette", "render",
    "render_batch", "save_image",
]
__version__ = "0.2.0"
