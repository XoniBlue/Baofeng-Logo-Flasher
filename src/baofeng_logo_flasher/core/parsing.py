"""
Centralized parsing helpers for offset and bitmap format values.

Both CLI and Streamlit must import these helpers rather than re-implement.
"""

from typing import Optional

from baofeng_logo_flasher.logo_codec import (
    BitmapFormat,
    parse_bitmap_format as _parse_bitmap_format_core,
    BITMAP_FORMAT_ALIASES,
)


def parse_offset(value: Optional[str]) -> Optional[int]:
    """
    Parse offset value from string, supporting multiple formats.

    This is the single source of truth for offset parsing.

    Accepts:
        - Decimal: "4096"
        - Hex with 0x prefix: "0x1000" or "0X1000"
        - Hex with h suffix: "1000h" or "1000H"
        - None for auto-detection

    Returns:
        Parsed integer offset, or None if value is None or empty.

    Raises:
        ValueError: If value cannot be parsed.
    """
    if value is None:
        return None

    value = value.strip()
    if not value:
        return None

    try:
        # Hex with 0x/0X prefix
        if value.lower().startswith("0x"):
            return int(value, 16)
        # Hex with h/H suffix
        if value.lower().endswith("h"):
            return int(value[:-1], 16)
        # Decimal
        return int(value)
    except ValueError:
        raise ValueError(
            f"Invalid offset '{value}'. Use decimal (4096), hex (0x1000), or suffix (1000h)."
        )


def parse_bitmap_format(value: str) -> BitmapFormat:
    """
    Parse bitmap format from user-friendly string.

    This is the single source of truth for bitmap format parsing.
    Wraps the core parser from logo_codec.

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
    return _parse_bitmap_format_core(value)


def get_valid_bitmap_formats() -> list:
    """Get list of valid bitmap format strings."""
    return sorted(BITMAP_FORMAT_ALIASES.keys())


def parse_size(value: str) -> tuple:
    """
    Parse size string in WxH format.

    Args:
        value: Size string like "128x64" or "160x128"

    Returns:
        Tuple of (width, height)

    Raises:
        ValueError: If format is invalid
    """
    try:
        parts = value.lower().split('x')
        if len(parts) != 2:
            raise ValueError()
        return (int(parts[0]), int(parts[1]))
    except ValueError:
        raise ValueError(
            f"Invalid size format '{value}'. Use WxH format like '128x64'."
        )
