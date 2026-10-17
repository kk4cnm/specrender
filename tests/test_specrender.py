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


# --------------------------------------------------------------------------- #
# HTML player
# --------------------------------------------------------------------------- #
import base64
import json
import re


def _player_cfg(page: str) -> dict:
    m = re.search(r'<script type="application/json">(.*?)</script>', page, re.S)
    return json.loads(m.group(1))


def test_player_self_contained(tmp_path, stereo_wav):
    out = tmp_path / "p.html"
    page = sr.player(stereo_wav, out, channel="all", scale="log", palette="viridis", height=240)
    assert out.read_text(encoding="utf-8") == page
    assert "customElements.define(\"spectro-player\"" in page
    cfg = _player_cfg(page)
    assert cfg["duration"] == pytest.approx(1.0)
    assert cfg["title"] == "stereo.wav" and cfg["height"] == 240
    assert len(cfg["channels"]) == 2 and cfg["channels"][0]["top"] == 0
    assert cfg["image"].startswith("data:image/png;base64,")
    assert cfg["audio"].startswith("data:audio/wav;base64,")   # original WAV embedded as-is
    assert base64.b64decode(cfg["audio"].split(",", 1)[1]) == stereo_wav.read_bytes()
    assert all(0 <= t["pos"] <= 1 for t in cfg["yticks"]) and len(cfg["yticks"]) >= 2


def test_player_crop_reencodes_segment(stereo_wav):
    cfg = _player_cfg(sr.player(stereo_wav, start=0.25, end=0.75, audio="wav"))
    assert cfg["duration"] == pytest.approx(0.5) and cfg["time_offset"] == pytest.approx(0.25)
    wav = base64.b64decode(cfg["audio"].split(",", 1)[1])
    from scipy.io import wavfile
    rate, data = wavfile.read(io.BytesIO(wav))
    assert rate == FS and data.shape == (FS // 2, 2)   # stereo kept even though the view is a mix


def test_player_array_and_audio_url():
    cfg = _player_cfg(sr.player(tone(500), sample_rate=FS, audio_url="https://example.com/a.mp3", start=0.2))
    assert cfg["audio"] == "https://example.com/a.mp3" and cfg["audio_offset"] == pytest.approx(0.2)
    cfg = _player_cfg(sr.player(tone(500), sample_rate=FS, audio="wav"))
    assert cfg["audio"].startswith("data:audio/wav")


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_player_compresses_when_large(stereo_wav):
    cfg = _player_cfg(sr.player(stereo_wav, max_embed_mb=0.001))
    assert cfg["audio"].startswith("data:audio/mpeg")


def test_player_script_breakout_is_escaped(stereo_wav):
    page = sr.player(stereo_wav, title="</script><b>x")
    assert "</script><b>" not in page.split('<script type="application/json">', 1)[1].split("</spectro-player>")[0]
    assert _player_cfg(page)["title"] == "</script><b>x"


def test_player_rejects_bad_options(stereo_wav):
    with pytest.raises(TypeError):
        sr.player(stereo_wav, colour="red")
    with pytest.raises(ValueError):
        sr.player(stereo_wav, annotate=True)


def test_export_player(tmp_path, stereo_wav):
    out = sr.export_player(stereo_wav, tmp_path / "web", image_format="webp")
    d = tmp_path / "web"
    assert {p.name for p in d.iterdir()} == {"stereo.webp", "stereo.json", "stereo.wav",
                                             "specrender-player.js", "stereo.html"}
    meta = json.loads((d / "stereo.json").read_text())
    assert meta["image"] == "stereo.webp" and meta["audio"] == "stereo.wav"
    assert out["embed"] == '<spectro-player meta="stereo.json"></spectro-player>'
    assert 'src="specrender-player.js"' in (d / "stereo.html").read_text()


def test_cli_html(tmp_path, stereo_wav):
    out = tmp_path / "cli.html"
    assert cli_main([str(stereo_wav), "-o", str(out), "-s", "mel", "-H", "200"]) == 0
    assert _player_cfg(out.read_text(encoding="utf-8"))["scale"] == "mel"
    assert cli_main([str(stereo_wav), "-f", "html", "--web", "-d", str(tmp_path / "w")]) == 0
    assert (tmp_path / "w" / "stereo.json").exists()


def test_player_js_ships_with_package():
    js = sr.player_js()
    assert "spectro-player" in js and len(js) > 5000


def test_export_player_cropped_never_overwrites_source(tmp_path):
    src = tmp_path / "rec.wav"
    wavfile.write(src, FS, (tone(800, 2.0) * 32767).astype(np.int16))
    before = src.read_bytes()
    out = sr.export_player(src, tmp_path, start=0.5, end=1.0, audio="wav")
    assert src.read_bytes() == before                       # source untouched
    assert out["audio"].name == "rec.player.wav"
    meta = json.loads(out["meta"].read_text())
    assert meta["audio"] == "rec.player.wav" and meta["duration"] == pytest.approx(0.5)
    # uncropped export into the same folder just references the source
    out2 = sr.export_player(src, tmp_path)
    assert out2["audio"] == src and json.loads(out2["meta"].read_text())["audio"] == "rec.wav"


def test_export_player_urlencodes_names(tmp_path):
    src = tmp_path / "take #1.wav"
    wavfile.write(src, FS, (tone(800) * 32767).astype(np.int16))
    out = sr.export_player(src, tmp_path / "w")
    meta = json.loads(out["meta"].read_text())
    assert meta["image"] == "take%20%231.png" and meta["audio"] == "take%20%231.wav"
    assert out["embed"] == '<spectro-player meta="take%20%231.json"></spectro-player>'
    assert (tmp_path / "w" / "take #1.json").exists()
