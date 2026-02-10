"""
Logo image codec for Baofeng UV-5RM radios.

Converts PNG/JPG images to/from monochrome bitmap formats used by radio.
Supports multiple packing formats for flexibility (discovery phase).
"""

import logging
from enum import Enum
from typing import Tuple, Optional, Dict

import io
from PIL import Image, ImageOps, ImageDraw

logger = logging.getLogger(__name__)


class BitmapFormat(Enum):
    """Supported monochrome bitmap formats."""
    ROW_MAJOR_MSB = "row_msb"        # Row-major, MSB-first (most common)
    ROW_MAJOR_LSB = "row_lsb"        # Row-major, LSB-first
    PAGE_MAJOR_MSB = "page_msb"      # SSD1306-style column/page, MSB
    PAGE_MAJOR_LSB = "page_lsb"      # SSD1306-style column/page, LSB


# Alias mapping for user-friendly format names
# Maps normalized strings to BitmapFormat enum members
BITMAP_FORMAT_ALIASES: Dict[str, BitmapFormat] = {
    # Canonical enum names (lowercase)
    "row_major_msb": BitmapFormat.ROW_MAJOR_MSB,
    "row_major_lsb": BitmapFormat.ROW_MAJOR_LSB,
    "page_major_msb": BitmapFormat.PAGE_MAJOR_MSB,
    "page_major_lsb": BitmapFormat.PAGE_MAJOR_LSB,
    # Short aliases (match enum values)
    "row_msb": BitmapFormat.ROW_MAJOR_MSB,
    "row_lsb": BitmapFormat.ROW_MAJOR_LSB,
    "page_msb": BitmapFormat.PAGE_MAJOR_MSB,
    "page_lsb": BitmapFormat.PAGE_MAJOR_LSB,
}


def parse_bitmap_format(value: str) -> BitmapFormat:
    """
    Parse bitmap format from user-friendly string.

    This is the centralized format parser used by CLI, UI, and tools.

    Accepts canonical enum names and friendly aliases:
        - "ROW_MAJOR_MSB" or "row_msb" or "row-major-msb"
        - "ROW_MAJOR_LSB" or "row_lsb" or "row-major-lsb"
        - "PAGE_MAJOR_MSB" or "page_msb" or "page-major-msb"
        - "PAGE_MAJOR_LSB" or "page_lsb" or "page-major-lsb"

    Returns:
        Corresponding BitmapFormat enum value.

    Raises:
        ValueError: If format is not recognized.
    """
    # Normalize: lowercase, replace hyphens with underscores
    normalized = value.lower().strip().replace("-", "_")

    if normalized in BITMAP_FORMAT_ALIASES:
        return BITMAP_FORMAT_ALIASES[normalized]

    valid_formats = ", ".join(sorted(BITMAP_FORMAT_ALIASES.keys()))
    raise ValueError(
        f"Invalid bitmap format '{value}'. Valid formats: {valid_formats}"
    )


class LogoCodec:
    """Encode/decode logo images to/from packed bitmap format."""

    def __init__(
        self,
        format: BitmapFormat = BitmapFormat.ROW_MAJOR_MSB,
        dither: bool = False,
    ):
        """
        Initialize codec.

        Args:
            format: Bitmap packing format
            dither: Apply dithering when converting to monochrome (default False)
        """
        self.format = format
        self.dither = dither

    @staticmethod
    def load_image(image_path: str) -> Image.Image:
        """Load image from file."""
        img = Image.open(image_path)
        logger.debug(f"Loaded image: {img.size} {img.mode}")
        return img

    @staticmethod
    def resize_image(
        img: Image.Image,
        target_size: Tuple[int, int] = (128, 64),
    ) -> Image.Image:
        """
        Resize image to target dimensions.

        Args:
            img: Input image
            target_size: (width, height) tuple

        Returns:
            Resized image maintaining aspect ratio
        """
        logger.debug(f"Resizing from {img.size} to {target_size}")
        img.thumbnail(target_size, Image.Resampling.LANCZOS)

        # Paste onto white background if needed
        if img.size != target_size:
            bg = Image.new('RGB', target_size, 'white')
            offset = (
                (target_size[0] - img.size[0]) // 2,
                (target_size[1] - img.size[1]) // 2,
            )
            bg.paste(img, offset)
            img = bg

        return img

    @staticmethod
    def to_monochrome(
        img: Image.Image,
        dither: bool = False,
    ) -> Image.Image:
        """
        Convert image to 1-bit (black and white).

        Args:
            img: Input image (any color mode)
            dither: Use dithering (produces better looking results)

        Returns:
            1-bit monochrome image
        """
        # Ensure RGB
        if img.mode != 'RGB':
            img = img.convert('RGB')

        # Convert to 1-bit
        if dither:
            mono = img.convert('1', dither=Image.Dither.FLOYDSTEINBERG)
        else:
            # Simple threshold at 50%
            mono = img.convert('1')

        logger.debug(f"Converted to monochrome: {mono.mode} {mono.size}")
        return mono

    def _pack_row_msb(self, img: Image.Image) -> bytes:
        """Pack image as row-major, MSB-first."""
        width, height = img.size
        pixels = img.load()

        data = bytearray()

        for y in range(height):
            for x in range(0, width, 8):
                byte_val = 0
                for bit in range(8):
                    if x + bit < width:
                        pixel = pixels[x + bit, y]
                        # pixel is 0 (black) or 255 (white) in 1-bit image
                        bit_val = 1 if pixel == 0 else 0
                        byte_val |= (bit_val << (7 - bit))
                data.append(byte_val)

        return bytes(data)

    def _pack_row_lsb(self, img: Image.Image) -> bytes:
        """Pack image as row-major, LSB-first."""
        width, height = img.size
        pixels = img.load()

        data = bytearray()

        for y in range(height):
            for x in range(0, width, 8):
                byte_val = 0
                for bit in range(8):
                    if x + bit < width:
                        pixel = pixels[x + bit, y]
                        bit_val = 1 if pixel == 0 else 0
                        byte_val |= (bit_val << bit)
                data.append(byte_val)

        return bytes(data)

    def _pack_page_msb(self, img: Image.Image) -> bytes:
        """Pack image as page-major (SSD1306-style), MSB-first."""
        width, height = img.size
        pixels = img.load()

        data = bytearray()
        pages = (height + 7) // 8

        for page in range(pages):
            for x in range(width):
                byte_val = 0
                for bit in range(8):
                    y = page * 8 + bit
                    if y < height:
                        pixel = pixels[x, y]
                        bit_val = 1 if pixel == 0 else 0
                        byte_val |= (bit_val << (7 - bit))
                data.append(byte_val)

        return bytes(data)

    def _pack_page_lsb(self, img: Image.Image) -> bytes:
        """Pack image as page-major (SSD1306-style), LSB-first."""
        width, height = img.size
        pixels = img.load()

        data = bytearray()
        pages = (height + 7) // 8

        for page in range(pages):
            for x in range(width):
                byte_val = 0
                for bit in range(8):
                    y = page * 8 + bit
                    if y < height:
                        pixel = pixels[x, y]
                        bit_val = 1 if pixel == 0 else 0
                        byte_val |= (bit_val << bit)
                data.append(byte_val)

        return bytes(data)

    def pack(self, img: Image.Image) -> bytes:
        """
        Pack monochrome image to bytes.

        Args:
            img: 1-bit monochrome PIL Image

        Returns:
            Packed bitmap bytes
        """
        if img.mode != '1':
            raise ValueError(f"Expected 1-bit image, got {img.mode}")

        logger.debug(f"Packing {img.size} image as {self.format.value}")

        if self.format == BitmapFormat.ROW_MAJOR_MSB:
            return self._pack_row_msb(img)
        elif self.format == BitmapFormat.ROW_MAJOR_LSB:
            return self._pack_row_lsb(img)
        elif self.format == BitmapFormat.PAGE_MAJOR_MSB:
            return self._pack_page_msb(img)
        elif self.format == BitmapFormat.PAGE_MAJOR_LSB:
            return self._pack_page_lsb(img)
        else:
            raise ValueError(f"Unknown format: {self.format}")

    def _unpack_row_msb(self, data: bytes, width: int, height: int) -> Image.Image:
        """Unpack row-major MSB-first data to image."""
        bytes_per_row = (width + 7) // 8
        img = Image.new('1', (width, height), 1)
        pixels = img.load()

        white = 1
        for y in range(height):
            for x in range(width):
                byte_idx = y * bytes_per_row + (x // 8)
                if byte_idx < len(data):
                    bit_idx = 7 - (x % 8)
                    bit = (data[byte_idx] >> bit_idx) & 1
                    pixels[x, y] = 0 if bit else white

        return img

    def _unpack_row_lsb(self, data: bytes, width: int, height: int) -> Image.Image:
        """Unpack row-major LSB-first data to image."""
        bytes_per_row = (width + 7) // 8
        img = Image.new('1', (width, height), 1)
        pixels = img.load()

        white = 1
        for y in range(height):
            for x in range(width):
                byte_idx = y * bytes_per_row + (x // 8)
                if byte_idx < len(data):
                    bit_idx = x % 8
                    bit = (data[byte_idx] >> bit_idx) & 1
                    pixels[x, y] = 0 if bit else white

        return img

    def _unpack_page_msb(self, data: bytes, width: int, height: int) -> Image.Image:
        """Unpack page-major MSB-first data to image."""
        img = Image.new('1', (width, height), 1)
        pixels = img.load()

        white = 1
        for page in range((height + 7) // 8):
            for x in range(width):
                byte_idx = page * width + x
                if byte_idx < len(data):
                    byte_val = data[byte_idx]
                    for bit in range(8):
                        y = page * 8 + bit
                        if y < height:
                            bit_val = (byte_val >> (7 - bit)) & 1
                            pixels[x, y] = 0 if bit_val else white

        return img

    def _unpack_page_lsb(self, data: bytes, width: int, height: int) -> Image.Image:
        """Unpack page-major LSB-first data to image."""
        img = Image.new('1', (width, height), 1)
        pixels = img.load()

        white = 1
        for page in range((height + 7) // 8):
            for x in range(width):
                byte_idx = page * width + x
                if byte_idx < len(data):
                    byte_val = data[byte_idx]
                    for bit in range(8):
                        y = page * 8 + bit
                        if y < height:
                            bit_val = (byte_val >> bit) & 1
                            pixels[x, y] = 0 if bit_val else white

        return img

    def unpack(self, data: bytes, width: int, height: int) -> Image.Image:
        """
        Unpack bitmap bytes to image for preview.

        Args:
            data: Packed bitmap bytes
            width: Image width
            height: Image height

        Returns:
            1-bit PIL Image
        """
        logger.debug(f"Unpacking {len(data)} bytes to {width}x{height} {self.format.value}")

        if self.format == BitmapFormat.ROW_MAJOR_MSB:
            return self._unpack_row_msb(data, width, height)
        elif self.format == BitmapFormat.ROW_MAJOR_LSB:
            return self._unpack_row_lsb(data, width, height)
        elif self.format == BitmapFormat.PAGE_MAJOR_MSB:
            return self._unpack_page_msb(data, width, height)
        elif self.format == BitmapFormat.PAGE_MAJOR_LSB:
            return self._unpack_page_lsb(data, width, height)
        else:
            raise ValueError(f"Unknown format: {self.format}")

    def convert_image(
        self,
        input_path: str,
        target_size: Tuple[int, int] = (128, 64),
    ) -> bytes:
        """
        Complete pipeline: load → resize → monochrome → pack.

        Args:
            input_path: Path to PNG/JPG file
            target_size: Target (width, height)

        Returns:
            Packed bitmap bytes
        """
        img = self.load_image(input_path)
        img = self.resize_image(img, target_size)
        img = self.to_monochrome(img, self.dither)
        data = self.pack(img)

        logger.info(f"Converted {input_path} to {len(data)} packed bytes "
                    f"({target_size[0]}x{target_size[1]} {self.format.value})")

        return data
