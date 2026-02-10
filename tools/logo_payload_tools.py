#!/usr/bin/env python3
"""
Utilities for byte-true inspection and comparison of UV-5RM A5 logo payloads.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import List, Tuple

from PIL import Image

from baofeng_logo_flasher.protocol.logo_protocol import (
    IMAGE_WIDTH,
    IMAGE_HEIGHT,
    build_write_frames,
    convert_image_to_rgb565,
    dump_logo_debug_artifacts,
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _extract_payload_from_a5_frames(stream: bytes) -> bytes:
    """
    Extract concatenated CMD_WRITE payloads from a contiguous A5 frame stream.
    """
    payload = bytearray()
    i = 0
    while i + 8 <= len(stream):
        if stream[i] != 0xA5:
            i += 1
            continue
        cmd = stream[i + 1]
        length = (stream[i + 4] << 8) | stream[i + 5]
        frame_len = 1 + 1 + 2 + 2 + length + 2
        if i + frame_len > len(stream):
            break
        frame_payload = stream[i + 6:i + 6 + length]
        if cmd == 0x57:
            payload.extend(frame_payload)
        i += frame_len
    return bytes(payload)


def _to_payload(data: bytes, kind: str) -> bytes:
    if kind == "raw-payload":
        return data
    if kind == "write-payload-stream":
        return data
    if kind == "a5-frames":
        return _extract_payload_from_a5_frames(data)
    raise ValueError(f"Unknown kind: {kind}")


def _render_rgb565(payload: bytes, layout: str, width: int, height: int) -> Image.Image:
    total = width * height
    words: List[int] = []
    for i in range(0, len(payload) - 1, 2):
        words.append(payload[i] | (payload[i + 1] << 8))
    if len(words) < total:
        words.extend([0] * (total - len(words)))
    words = words[:total]

    img = Image.new("RGB", (width, height))
    px = img.load()

    def _decode(val: int) -> Tuple[int, int, int]:
        b5 = (val >> 11) & 0x1F
        g6 = (val >> 5) & 0x3F
        r5 = val & 0x1F
        r = (r5 << 3) | (r5 >> 2)
        g = (g6 << 2) | (g6 >> 4)
        b = (b5 << 3) | (b5 >> 2)
        return (r, g, b)

    for idx, val in enumerate(words):
        if layout == "row-major":
            x = idx % width
            y = idx // width
        elif layout == "row-major-swapped-wh":
            # Interpret stream as if source dimensions were height x width.
            x = idx // height
            y = idx % height
        elif layout == "column-major":
            x = idx // height
            y = idx % height
        else:
            raise ValueError(f"Unknown layout: {layout}")

        if 0 <= x < width and 0 <= y < height:
            px[x, y] = _decode(val)

    return img


def cmd_emit(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    image_data = convert_image_to_rgb565(args.image, size=(args.width, args.height))
    frames = build_write_frames(image_data, chunk_size=args.chunk_size, pad_last_chunk=False)

    manifest_path = dump_logo_debug_artifacts(image_data, frames, str(out_dir))
    print(f"wrote: {manifest_path}")
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    ours_raw = Path(args.ours).read_bytes()
    theirs_raw = Path(args.theirs).read_bytes()

    ours = _to_payload(ours_raw, args.ours_kind)
    theirs = _to_payload(theirs_raw, args.theirs_kind)

    if args.limit is not None:
        ours = ours[:args.limit]
        theirs = theirs[:args.limit]

    report = {
        "ours_len": len(ours),
        "theirs_len": len(theirs),
        "ours_sha256": _sha256(ours),
        "theirs_sha256": _sha256(theirs),
        "equal": ours == theirs,
    }

    if ours != theirs:
        max_len = min(len(ours), len(theirs))
        first_diff = next((i for i in range(max_len) if ours[i] != theirs[i]), None)
        report["first_diff"] = first_diff
        if first_diff is not None:
            report["ours_byte"] = ours[first_diff]
            report["theirs_byte"] = theirs[first_diff]

    print(json.dumps(report, indent=2))
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    raw = Path(args.input).read_bytes()
    payload = _to_payload(raw, args.input_kind)
    img = _render_rgb565(payload, args.layout, args.width, args.height)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print(f"wrote: {out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_emit = sub.add_parser("emit", help="Emit local payload/frame artifacts from an image")
    p_emit.add_argument("--image", required=True, help="Input image file")
    p_emit.add_argument("--out-dir", required=True, help="Output directory")
    p_emit.add_argument("--width", type=int, default=IMAGE_WIDTH)
    p_emit.add_argument("--height", type=int, default=IMAGE_HEIGHT)
    p_emit.add_argument("--chunk-size", type=int, default=1024)
    p_emit.set_defaults(func=cmd_emit)

    kinds = ["raw-payload", "write-payload-stream", "a5-frames"]
    p_compare = sub.add_parser("compare", help="Compare normalized payload bytes")
    p_compare.add_argument("--ours", required=True, help="Our binary input path")
    p_compare.add_argument("--ours-kind", required=True, choices=kinds)
    p_compare.add_argument("--theirs", required=True, help="CPS/pcap-derived binary path")
    p_compare.add_argument("--theirs-kind", required=True, choices=kinds)
    p_compare.add_argument("--limit", type=int, default=None, help="Optional compare prefix length")
    p_compare.set_defaults(func=cmd_compare)

    p_render = sub.add_parser("render", help="Render payload bytes as an image")
    p_render.add_argument("--input", required=True, help="Input binary path")
    p_render.add_argument("--input-kind", required=True, choices=kinds)
    p_render.add_argument("--out", required=True, help="Output PNG path")
    p_render.add_argument("--layout", choices=["row-major", "row-major-swapped-wh", "column-major"], default="row-major")
    p_render.add_argument("--width", type=int, default=IMAGE_WIDTH)
    p_render.add_argument("--height", type=int, default=IMAGE_HEIGHT)
    p_render.set_defaults(func=cmd_render)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
