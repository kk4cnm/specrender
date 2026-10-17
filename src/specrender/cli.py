"""Command-line interface: ``specrender input.wav -o out.png --width 1200 ...``"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .core import compute, save_image
from .palettes import list_palettes


def _db_range(s: str) -> tuple[float, float]:
    try:
        lo, hi = (float(v) for v in s.split(":"))
    except ValueError:
        raise argparse.ArgumentTypeError("use LOW:HIGH, e.g. -90:0") from None
    return lo, hi


def _channel(s: str):
    return int(s) if s.lstrip("-").isdigit() else s


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="specrender", description="Render spectrogram images from audio files.")
    p.add_argument("inputs", nargs="*", type=Path, help="audio file(s)")
    p.add_argument("-o", "--output", type=Path, help="output file (single input only)")
    p.add_argument("-d", "--out-dir", type=Path, help="output directory (default: next to input)")
    p.add_argument("-f", "--format", default=None, help="png, jpg, webp, bmp, tiff, gif (default: from -o or png)")
    p.add_argument("-q", "--quality", type=int, default=92, help="JPEG/WebP quality (default 92)")

    g = p.add_argument_group("size & look")
    g.add_argument("-W", "--width", type=int, default=1200, help="output width in pixels (default 1200)")
    g.add_argument("-H", "--height", type=int, default=400, help="output height in pixels (default 400)")
    g.add_argument("-p", "--palette", default="magma", help="palette name, or comma-separated hex colors (default magma)")
    g.add_argument("-r", "--dynamic-range", type=float, default=80.0, help="dB below the peak shown (default 80)")
    g.add_argument("--db-range", type=_db_range, help="fixed dBFS range LOW:HIGH (consistent across files)")
    g.add_argument("--gamma", type=float, default=1.0, help=">1 brightens quiet detail")
    g.add_argument("-a", "--annotate", action="store_true", help="add axes, labels and colorbar (needs matplotlib)")
    g.add_argument("--title", help="title for --annotate (use {name} for the file name)")
    g.add_argument("--light", action="store_true", help="light theme for --annotate")

    a = p.add_argument_group("analysis")
    a.add_argument("-s", "--scale", choices=["linear", "log", "mel"], default="linear", help="frequency axis (default linear)")
    a.add_argument("--fmin", type=float, help="lowest frequency, Hz")
    a.add_argument("--fmax", type=float, help="highest frequency, Hz")
    a.add_argument("--start", type=float, default=0.0, help="seconds")
    a.add_argument("--end", type=float, help="seconds")
    a.add_argument("-n", "--n-fft", type=int, default=2048, help="FFT size (default 2048)")
    a.add_argument("--hop", type=int, help="hop length in samples (default n_fft/4)")
    a.add_argument("--window", default="hann", help="scipy window name (default hann)")
    a.add_argument("-c", "--channel", type=_channel, default="mix",
                   help="mix, left, right, side, all, or an index")
    a.add_argument("--aggregate", choices=["max", "mean"], default="max", help="downscaling: max keeps short events (default)")
    a.add_argument("--pre-emphasis", type=float, default=0.0, help="e.g. 0.97 for speech")

    p.add_argument("--list-palettes", action="store_true", help="list palette names and exit")
    p.add_argument("--version", action="version", version=f"specrender {__version__}")
    return p


def _join_negative_values(argv: list[str]) -> list[str]:
    """Let ``--db-range -90:0`` work (argparse would read -90:0 as an option)."""
    out, i = [], 0
    while i < len(argv):
        if argv[i] == "--db-range" and i + 1 < len(argv):
            out.append(f"--db-range={argv[i + 1]}")
            i += 2
        else:
            out.append(argv[i])
            i += 1
    return out


def main(argv=None) -> int:
    argv = _join_negative_values(list(sys.argv[1:] if argv is None else argv))
    args = build_parser().parse_args(argv)
    if args.list_palettes:
        print("\n".join(list_palettes(include_matplotlib=True)))
        return 0
    if not args.inputs:
        build_parser().error("no input files")
    if args.output and len(args.inputs) > 1:
        build_parser().error("-o works with a single input; use --out-dir for several")

    palette = args.palette.split(",") if "," in args.palette or args.palette.startswith("#") else args.palette
    fmt = (args.format or (args.output.suffix.lstrip(".") if args.output else "png")).lower()

    failures = 0
    for src in args.inputs:
        if args.output:
            dst = args.output
        else:
            dst = (args.out_dir or src.parent) / f"{src.stem}.{fmt}"
        try:
            spec = compute(
                src, channel=args.channel, start=args.start, end=args.end, n_fft=args.n_fft,
                hop_length=args.hop, window=args.window, scale=args.scale, fmin=args.fmin,
                fmax=args.fmax, width=args.width, height=args.height,
                aggregate=args.aggregate, pre_emphasis=args.pre_emphasis,
            )
            img = spec.to_image(
                width=args.width, height=args.height, palette=palette,
                dynamic_range=args.dynamic_range, db_range=args.db_range, gamma=args.gamma,
                annotate=args.annotate, theme="light" if args.light else "dark",
                title=args.title.format(name=src.name) if args.title else None,
            )
            save_image(img, dst, format=args.format, quality=args.quality)
            print(f"{src} -> {dst}")
        except Exception as e:  # keep going through a batch
            failures += 1
            print(f"error: {src}: {e}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
