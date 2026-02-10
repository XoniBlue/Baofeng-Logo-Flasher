#!/usr/bin/env python3
"""
Generate deterministic 160x128 RGB probe images for radio layout debugging.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw


W, H = 160, 128


def _save(img: Image.Image, out_dir: Path, name: str) -> None:
    path = out_dir / f"{name}.png"
    img.save(path)
    print(f"wrote: {path}")


def probe_quadrants() -> Image.Image:
    img = Image.new("RGB", (W, H), "black")
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W // 2 - 1, H // 2 - 1), fill=(255, 0, 0))
    d.rectangle((W // 2, 0, W - 1, H // 2 - 1), fill=(0, 255, 0))
    d.rectangle((0, H // 2, W // 2 - 1, H - 1), fill=(0, 0, 255))
    d.rectangle((W // 2, H // 2, W - 1, H - 1), fill=(255, 255, 255))
    return img


def probe_h_stripes() -> Image.Image:
    img = Image.new("RGB", (W, H), "black")
    d = ImageDraw.Draw(img)
    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]
    stripe_h = 8
    for y in range(0, H, stripe_h):
        c = colors[(y // stripe_h) % len(colors)]
        d.rectangle((0, y, W - 1, min(H - 1, y + stripe_h - 1)), fill=c)
    return img


def probe_v_stripes() -> Image.Image:
    img = Image.new("RGB", (W, H), "black")
    d = ImageDraw.Draw(img)
    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]
    stripe_w = 8
    for x in range(0, W, stripe_w):
        c = colors[(x // stripe_w) % len(colors)]
        d.rectangle((x, 0, min(W - 1, x + stripe_w - 1), H - 1), fill=c)
    return img


def probe_row_index() -> Image.Image:
    img = Image.new("RGB", (W, H), "black")
    px = img.load()
    for y in range(H):
        v = int((y / (H - 1)) * 255)
        for x in range(W):
            px[x, y] = (v, 255 - v, (v // 2))
    return img


def probe_col_index() -> Image.Image:
    img = Image.new("RGB", (W, H), "black")
    px = img.load()
    for x in range(W):
        v = int((x / (W - 1)) * 255)
        for y in range(H):
            px[x, y] = (v, (v // 2), 255 - v)
    return img


def probe_text_grid() -> Image.Image:
    img = Image.new("RGB", (W, H), (20, 20, 20))
    d = ImageDraw.Draw(img)
    for y in range(0, H, 16):
        d.line((0, y, W - 1, y), fill=(120, 120, 120))
    for x in range(0, W, 16):
        d.line((x, 0, x, H - 1), fill=(120, 120, 120))
    d.rectangle((0, 0, W - 1, H - 1), outline=(255, 255, 255), width=1)
    d.text((4, 4), "TL", fill=(255, 0, 0))
    d.text((W - 20, 4), "TR", fill=(0, 255, 0))
    d.text((4, H - 16), "BL", fill=(0, 0, 255))
    d.text((W - 20, H - 16), "BR", fill=(255, 255, 0))
    return img


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default="out/probes", help="Output directory")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    _save(probe_quadrants(), out_dir, "probe_01_quadrants")
    _save(probe_h_stripes(), out_dir, "probe_02_h_stripes")
    _save(probe_v_stripes(), out_dir, "probe_03_v_stripes")
    _save(probe_row_index(), out_dir, "probe_04_row_index")
    _save(probe_col_index(), out_dir, "probe_05_col_index")
    _save(probe_text_grid(), out_dir, "probe_06_text_grid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
