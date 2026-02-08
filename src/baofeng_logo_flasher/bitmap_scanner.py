"""
Bitmap candidate scanner for clone images.

Provides shared scanning logic for CLI tools and the Streamlit UI.
"""

from pathlib import Path
from typing import List, Tuple, Dict, Optional

from PIL import Image


# Common logo resolutions
CANDIDATE_SIZES = [
    (128, 64),
    (128, 32),
    (160, 80),
    (160, 128),
    (240, 128),
]


def bits_to_image_row_msb(row_bytes: bytes) -> List[int]:
    """Convert row bytes to pixels (MSB-first = left-to-right pixels in byte)."""
    pixels = []
    for byte_val in row_bytes:
        for bit in range(7, -1, -1):
            pixels.append((byte_val >> bit) & 1)
    return pixels


def bits_to_image_row_lsb(row_bytes: bytes) -> List[int]:
    """Convert row bytes to pixels (LSB-first = bit 0 is leftmost)."""
    pixels = []
    for byte_val in row_bytes:
        for bit in range(8):
            pixels.append((byte_val >> bit) & 1)
    return pixels


def convert_row_major_msb(data: bytes, width: int, height: int) -> Image.Image:
    """Row-major, MSB-first layout."""
    bytes_per_row = (width + 7) // 8
    img = Image.new('1', (width, height), 1)
    pixels = img.load()

    for row in range(height):
        row_offset = row * bytes_per_row
        row_data = data[row_offset:row_offset + bytes_per_row]
        row_pixels = bits_to_image_row_msb(row_data)

        for col in range(width):
            if col < len(row_pixels):
                pixels[col, row] = row_pixels[col]

    return img


def convert_row_major_lsb(data: bytes, width: int, height: int) -> Image.Image:
    """Row-major, LSB-first layout."""
    bytes_per_row = (width + 7) // 8
    img = Image.new('1', (width, height), 1)
    pixels = img.load()

    for row in range(height):
        row_offset = row * bytes_per_row
        row_data = data[row_offset:row_offset + bytes_per_row]
        row_pixels = bits_to_image_row_lsb(row_data)

        for col in range(width):
            if col < len(row_pixels):
                pixels[col, row] = row_pixels[col]

    return img


def convert_page_major_msb(data: bytes, width: int, height: int) -> Image.Image:
    """Column/page-major, MSB-first (SSD1306-style)."""
    bytes_per_page = width
    pages = (height + 7) // 8

    img = Image.new('1', (width, height), 1)
    pixels = img.load()

    for page in range(pages):
        for x in range(width):
            page_offset = page * bytes_per_page + x
            if page_offset < len(data):
                byte_val = data[page_offset]

                for bit in range(8):
                    y = page * 8 + bit
                    if y < height:
                        pixel = (byte_val >> (7 - bit)) & 1
                        pixels[x, y] = pixel

    return img


def convert_page_major_lsb(data: bytes, width: int, height: int) -> Image.Image:
    """Column/page-major, LSB-first."""
    bytes_per_page = width
    pages = (height + 7) // 8

    img = Image.new('1', (width, height), 1)
    pixels = img.load()

    for page in range(pages):
        for x in range(width):
            page_offset = page * bytes_per_page + x
            if page_offset < len(data):
                byte_val = data[page_offset]

                for bit in range(8):
                    y = page * 8 + bit
                    if y < height:
                        pixel = (byte_val >> bit) & 1
                        pixels[x, y] = pixel

    return img


def count_black_pixels(img: Image.Image) -> int:
    """Count black pixels in image."""
    pixels = img.load()
    count = 0
    for y in range(img.height):
        for x in range(img.width):
            if pixels[x, y] == 0:
                count += 1
    return count


def scan_bytes(
    data: bytes,
    max_candidates: int = 20,
    step: int = 16,
    sizes: Optional[List[Tuple[int, int]]] = None,
) -> List[Dict]:
    """Scan bytes for potential logo candidates."""
    if sizes is None:
        sizes = CANDIDATE_SIZES

    size = len(data)
    candidates: List[Dict] = []

    for width, height in sizes:
        bytes_needed = (width * height + 7) // 8

        for offset in range(0, size - bytes_needed, step):
            img_data = data[offset:offset + bytes_needed]
            if len(img_data) < bytes_needed:
                continue

            results = [
                ("row_msb", convert_row_major_msb(img_data, width, height)),
                ("row_lsb", convert_row_major_lsb(img_data, width, height)),
                ("page_msb", convert_page_major_msb(img_data, width, height)),
                ("page_lsb", convert_page_major_lsb(img_data, width, height)),
            ]

            for fmt_name, img in results:
                nonzero = count_black_pixels(img)
                total = img.width * img.height
                fill_ratio = nonzero / total if total > 0 else 0

                if 0.1 < fill_ratio < 0.9:
                    score = min(fill_ratio, 1 - fill_ratio)
                    candidates.append({
                        "offset": offset,
                        "width": width,
                        "height": height,
                        "format": fmt_name,
                        "fill_ratio": fill_ratio,
                        "score": score,
                        "image": img,
                    })

    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates[:max_candidates]


def save_candidates(candidates: List[Dict], out_dir: Path) -> List[Path]:
    """Save candidate images to disk and return their paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: List[Path] = []

    for i, cand in enumerate(candidates, 1):
        offset = cand["offset"]
        width = cand["width"]
        height = cand["height"]
        fmt = cand["format"]

        png_name = f"candidate_{i}_offset0x{offset:05X}_{width}x{height}_{fmt}.png"
        png_path = out_dir / png_name
        cand["image"].save(png_path)
        paths.append(png_path)

    return paths
