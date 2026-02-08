#!/usr/bin/env python3
"""
Scan clone image for candidate logo bitmap regions.

Analyzes image for likely monochrome logo blocks at common resolutions
(128x64, 160x80, etc.) and exports PNG previews for visual inspection.

Supports 4 common bitmap formats:
- Row-major 1bpp MSB-first (most common)
- Row-major 1bpp LSB-first
- Column/page-major 1bpp MSB-first (SSD1306-style)
- Column/page-major 1bpp LSB-first

Usage:
    python tools/scan_bitmap_candidates.py path/to/clone.img
    python tools/scan_bitmap_candidates.py Baofeng_5RM_20260204.img
"""

import sys
from pathlib import Path

from baofeng_logo_flasher.bitmap_scanner import (
    CANDIDATE_SIZES,
    scan_bytes,
    save_candidates,
)


def scan_image(filepath: str, max_candidates: int = 20) -> None:
    """Scan image for logo candidates."""
    path = Path(filepath)

    if not path.exists():
        print(f"ERROR: {filepath} not found", file=sys.stderr)
        sys.exit(1)

    data = path.read_bytes()
    size = len(data)

    print(f"\n{'=' * 70}")
    print(f"BITMAP CANDIDATE SCAN: {path.name}")
    print(f"File size: {size:,} bytes")
    print(f"{'=' * 70}\n")

    candidates = scan_bytes(data, max_candidates=max_candidates, step=16, sizes=CANDIDATE_SIZES)

    print(f"Found {len(candidates)} good candidates (showing top {len(candidates)}):\n")

    out_dir = Path("out/previews")
    paths = save_candidates(candidates, out_dir)

    for i, cand in enumerate(candidates, 1):
        offset = cand['offset']
        width = cand['width']
        height = cand['height']
        fmt = cand['format']
        fill = cand['fill_ratio']
        score = cand['score']
        png_path = paths[i - 1]

        print(f"{i}. Offset: 0x{offset:05X} | {width}x{height} | {fmt:9s} | "
              f"Fill: {fill*100:5.1f}% | Score: {score:.3f}")
        print(f"   → {png_path}")

    print()
    print("NEXT STEPS:")
    print("  1. Open each PNG in out/previews/ and visually inspect")
    print("  2. Look for recognizable logo or UI elements")
    print("  3. Once identified, use that offset + format for logo patching")
    print("  4. Example: patch logo at 0x005A0 with row-major MSB format")
    print()
    print(f"Output directory: {out_dir.absolute()}")
    print()
    print("=" * 70 + "\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tools/scan_bitmap_candidates.py <image.img>", file=sys.stderr)
        sys.exit(1)

    scan_image(sys.argv[1])
