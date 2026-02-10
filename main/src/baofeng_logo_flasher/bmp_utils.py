"""BMP validation and conversion utilities for boot logo images."""

from dataclasses import dataclass
from typing import Tuple
import io
import struct

from PIL import Image


@dataclass(frozen=True)
class BmpInfo:
    width: int
    height: int
    bits_per_pixel: int
    compression: int
    data_offset: int
    file_size: int
    image_size: int
    top_down: bool


def _row_size_bytes(width: int, bits_per_pixel: int) -> int:
    return ((bits_per_pixel * width + 31) // 32) * 4


def parse_bmp_header(data: bytes, allow_partial: bool = False) -> BmpInfo:
    if len(data) < 54:
        raise ValueError("BMP too small to contain header")

    if data[0:2] != b"BM":
        raise ValueError("Missing BMP signature")

    file_size = struct.unpack_from("<I", data, 2)[0]
    data_offset = struct.unpack_from("<I", data, 10)[0]
    header_size = struct.unpack_from("<I", data, 14)[0]

    if header_size < 40:
        raise ValueError("Unsupported BMP header size")

    width = struct.unpack_from("<i", data, 18)[0]
    height = struct.unpack_from("<i", data, 22)[0]
    planes = struct.unpack_from("<H", data, 26)[0]
    bits_per_pixel = struct.unpack_from("<H", data, 28)[0]
    compression = struct.unpack_from("<I", data, 30)[0]
    image_size = struct.unpack_from("<I", data, 34)[0]

    if planes != 1:
        raise ValueError("Invalid BMP planes value")

    if bits_per_pixel != 24:
        raise ValueError("BMP must be 24-bit")

    if compression != 0:
        raise ValueError("BMP must be uncompressed (BI_RGB)")

    top_down = height < 0
    width_abs = abs(width)
    height_abs = abs(height)

    if width_abs == 0 or height_abs == 0:
        raise ValueError("Invalid BMP dimensions")

    row_size = _row_size_bytes(width_abs, bits_per_pixel)
    expected_image_size = row_size * height_abs

    if image_size == 0:
        image_size = expected_image_size
    elif image_size != expected_image_size:
        raise ValueError("BMP image size mismatch")

    if not allow_partial:
        if data_offset + expected_image_size > len(data):
            raise ValueError("BMP pixel data exceeds file length")

        if file_size != len(data):
            raise ValueError("BMP file size mismatch")

    return BmpInfo(
        width=width_abs,
        height=height_abs,
        bits_per_pixel=bits_per_pixel,
        compression=compression,
        data_offset=data_offset,
        file_size=file_size,
        image_size=image_size,
        top_down=top_down,
    )


def validate_bmp_bytes(data: bytes, expected_size: Tuple[int, int]) -> BmpInfo:
    info = parse_bmp_header(data, allow_partial=False)
    if (info.width, info.height) != expected_size:
        raise ValueError(
            f"BMP size {info.width}x{info.height} does not match expected "
            f"{expected_size[0]}x{expected_size[1]}"
        )
    return info


def convert_image_to_bmp_bytes(
    input_path: str,
    target_size: Tuple[int, int],
) -> bytes:
    img = Image.open(input_path)

    if img.mode != "RGB":
        img = img.convert("RGB")

    img.thumbnail(target_size, Image.Resampling.LANCZOS)

    if img.size != target_size:
        bg = Image.new("RGB", target_size, "white")
        offset = (
            (target_size[0] - img.size[0]) // 2,
            (target_size[1] - img.size[1]) // 2,
        )
        bg.paste(img, offset)
        img = bg

    buffer = io.BytesIO()
    img.save(buffer, format="BMP")
    data = buffer.getvalue()
    validate_bmp_bytes(data, target_size)
    return data
