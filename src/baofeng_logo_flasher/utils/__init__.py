"""
Utility modules for Baofeng Logo Flasher.

This package groups pure helpers that are shared across core logic and UIs.
"""

# Re-export submodules so `from ..utils import bmp_utils` works.
from . import bmp_utils as bmp_utils
from . import firmware_crypto as firmware_crypto
from . import firmware_tools as firmware_tools
from . import logo_codec as logo_codec

from .bmp_utils import BmpInfo, parse_bmp_header, validate_bmp_bytes, convert_image_to_bmp_bytes
from .crypto import Crypto
from .logo_codec import BitmapFormat, parse_bitmap_format, LogoCodec

__all__ = [
    # Submodules
    "bmp_utils",
    "firmware_crypto",
    "firmware_tools",
    "logo_codec",
    "BmpInfo",
    "parse_bmp_header",
    "validate_bmp_bytes",
    "convert_image_to_bmp_bytes",
    "BitmapFormat",
    "parse_bitmap_format",
    "LogoCodec",
    "Crypto",
]
