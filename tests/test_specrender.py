import io
import shutil
import subprocess

import numpy as np
import pytest
from PIL import Image
from scipy.io import wavfile

import specrender as sr
from specrender.cli import main as cli_main

FS = 16000


def tone(freq, seconds=1.0, amp=0.5, fs=FS):
    t = np.arange(int(seconds * fs)) / fs
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


@pytest.fixture
def stereo_wav(tmp_path):
    x = np.stack([tone(1000), tone(3000)], axis=1)
    p = tmp_path / "stereo.wav"
    wavfile.write(p, FS, (x * 32767).astype(np.int16))
    return p


@pytest.mark.parametrize("scale", ["linear", "log", "mel"])
def test_tone_lands_on_correct_row(scale):
    s = sr.compute(tone(2000), sample_rate=FS, scale=scale, height=200)
    peak_row = int(np.argmax(s.db[0].mean(axis=1)))
    assert abs(s.freqs[peak_row] - 2000) / 2000 < 0.05


def test_full_scale_sine_is_near_0_dbfs():
    s = sr.compute(tone(1000, amp=1.0), sample_rate=FS)
    assert -1.0 < s.db.max() < 0.5


@pytest.mark.parametrize("fmt", ["png", "jpg", "jpeg", "webp", "bmp", "tiff", "gif"])
def test_formats_and_exact_size(tmp_path, stereo_wav, fmt):
    out = tmp_path / f"o.{fmt}"
    sr.render(stereo_wav, out, width=321, height=123)
    with Image.open(out) as im:
        assert im.size == (321, 123)


@pytest.mark.parametrize("height", [100, 101, 203])
def test_stacked_channels_exact_height(stereo_wav, height):
    img = sr.render(stereo_wav, width=200, height=height, channel="all")
    assert img.size == (200, height)


def test_channel_selection(stereo_wav):
    left = sr.compute(stereo_wav, channel="left", height=100)
    right = sr.compute(stereo_wav, channel="right", height=100)
    assert abs(left.freqs[np.argmax(left.db[0].mean(1))] - 1000) < 100
    assert abs(right.freqs[np.argmax(right.db[0].mean(1))] - 3000) < 100
    assert sr.compute(stereo_wav, channel="all").channels == 2
    with pytest.raises(ValueError):
        sr.compute(stereo_wav, channel=5)


def test_array_orientation_and_crop():
    x = np.stack([tone(500, 2.0), tone(500, 2.0)], axis=1)  # (n, ch)
    s = sr.compute(x, sample_rate=FS, channel="all", start=0.5, end=1.5)
    assert s.channels == 2
    assert s.duration == pytest.approx(1.0)
    assert s.times[0] == pytest.approx(0.5)


def test_palettes():
    assert sr.get_palette("magma").shape == (256, 3)
    assert (sr.get_palette("gray_r")[0] == 255).all()
    lut = sr.get_palette(["#000000", (255, 0, 0)])
    assert tuple(lut[-1]) == (255, 0, 0)
    sr.register_palette("mine", ["#001122", "#ffeedd"])
    assert tuple(sr.get_palette("mine")[0]) == (0x00, 0x11, 0x22)
    with pytest.raises(ValueError):
        sr.get_palette("definitely_not_a_palette")


def test_fixed_db_range_is_consistent():
    loud = sr.compute(tone(1000, amp=0.9), sample_rate=FS, height=64)
    quiet = sr.compute(tone(1000, amp=0.09), sample_rate=FS, height=64)
    a = loud.to_image(db_range=(-80, 0), palette="gray")
    b = quiet.to_image(db_range=(-80, 0), palette="gray")
    assert np.asarray(a).max() > np.asarray(b).max()  # quieter file renders darker


def test_long_audio_pools_and_keeps_short_click():
    x = 0.001 * np.random.default_rng(0).standard_normal(FS * 120).astype(np.float32)
    mid = len(x) // 2
    x[mid:mid + 80] += 0.9
    s = sr.compute(x, sample_rate=FS, width=400, height=50)
    assert s.db.shape == (1, 50, 400)
    assert abs(int(np.argmax(s.db[0].max(0))) - 200) <= 1


def test_to_bytes():
    s = sr.compute(tone(1000), sample_rate=FS)
    assert s.to_bytes("PNG", width=50, height=20)[:4] == b"\x89PNG"
    assert s.to_bytes("JPEG", width=50, height=20)[:2] == b"\xff\xd8"


def test_unknown_option_rejected(stereo_wav):
    with pytest.raises(TypeError):
        sr.render(stereo_wav, colour="red")


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_mp3_via_ffmpeg(tmp_path, stereo_wav):
    mp3 = tmp_path / "s.mp3"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(stereo_wav), str(mp3)], check=True)
    s = sr.compute(mp3, channel="left", height=100)
    assert abs(s.freqs[np.argmax(s.db[0].mean(1))] - 1000) < 100


def test_annotated(stereo_wav):
    pytest.importorskip("matplotlib")
    img = sr.render(stereo_wav, width=640, height=360, annotate=True, title="t", scale="log")
    assert img.size == (640, 360)


def test_cli(tmp_path, stereo_wav):
    out = tmp_path / "cli.webp"
    assert cli_main([str(stereo_wav), "-o", str(out), "-W", "300", "-H", "100",
                     "-p", "#000000,#00ff00", "-s", "mel"]) == 0
    with Image.open(out) as im:
        assert im.size == (300, 100)
    assert cli_main([str(tmp_path / "missing.wav"), "-d", str(tmp_path)]) == 1


def test_render_batch_shared_levels(tmp_path):
    paths = []
    for name, amp in (("loud", 0.9), ("quiet", 0.05)):
        p = tmp_path / f"{name}.wav"
        wavfile.write(p, FS, tone(800, amp=amp))
        paths.append(p)
    out = sr.render_batch(paths, tmp_path / "out", format="jpg", width=120, height=60,
                          shared_levels=True, palette="gray")
    assert [p.name for p in out] == ["loud.jpg", "quiet.jpg"]
    loud, quiet = (np.asarray(Image.open(p)).max() for p in out)
    assert loud > quiet


def test_flac_via_soundfile(tmp_path):
    sf = pytest.importorskip("soundfile")
    p = tmp_path / "t.flac"
    sf.write(p, tone(1500), FS)
    s = sr.compute(p, height=100, start=0.2, end=0.8)
    assert abs(s.freqs[np.argmax(s.db[0].mean(1))] - 1500) < 100
    assert s.duration == pytest.approx(0.6, abs=1e-3)


def test_to_image_defaults_to_compute_size():
    # Short clip: fewer frames than 2*width, so no pooling happens
    s = sr.compute(tone(1000, 0.5), sample_rate=FS, width=480, height=90)
    assert s.to_image().size == (480, 90)
    assert s.to_image(width=100).size == (100, 90)


def test_cli_negative_db_range(tmp_path, stereo_wav):
    out = tmp_path / "r.png"
    assert cli_main([str(stereo_wav), "-o", str(out), "--db-range", "-90:0", "-W", "64", "-H", "32"]) == 0
    assert out.exists()
