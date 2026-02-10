"""Tests for CLI parsing functions and protocol verification."""

import pytest
from unittest.mock import MagicMock

import typer

from baofeng_logo_flasher.logo_codec import BitmapFormat


class TestParseBitmapFormatCore:
    """Test the core parse_bitmap_format in logo_codec.py (raises ValueError)."""

    def get_parse_format_core(self):
        """Import the core parse_bitmap_format from logo_codec."""
        from baofeng_logo_flasher.logo_codec import parse_bitmap_format
        return parse_bitmap_format

    def test_core_canonical_names(self):
        """Core function parses canonical enum names."""
        parse_format = self.get_parse_format_core()

        assert parse_format("ROW_MAJOR_MSB") == BitmapFormat.ROW_MAJOR_MSB
        assert parse_format("PAGE_MAJOR_LSB") == BitmapFormat.PAGE_MAJOR_LSB

    def test_core_short_aliases(self):
        """Core function parses short aliases."""
        parse_format = self.get_parse_format_core()

        assert parse_format("row_msb") == BitmapFormat.ROW_MAJOR_MSB
        assert parse_format("page_lsb") == BitmapFormat.PAGE_MAJOR_LSB

    def test_core_invalid_raises_valueerror(self):
        """Core function raises ValueError (not typer.BadParameter)."""
        parse_format = self.get_parse_format_core()

        with pytest.raises(ValueError):
            parse_format("invalid_format")

        with pytest.raises(ValueError):
            parse_format("")


class TestParseOffset:
    """Test offset parsing from various input formats."""

    def get_parse_offset(self):
        """Import parse_offset from cli module."""
        from baofeng_logo_flasher.cli import parse_offset
        return parse_offset

    def test_parse_offset_none(self):
        """None input returns None."""
        parse_offset = self.get_parse_offset()
        assert parse_offset(None) is None

    def test_parse_offset_empty_string(self):
        """Empty string returns None."""
        parse_offset = self.get_parse_offset()
        assert parse_offset("") is None
        assert parse_offset("  ") is None

    def test_parse_offset_decimal(self):
        """Decimal integer strings are parsed correctly."""
        parse_offset = self.get_parse_offset()
        assert parse_offset("4096") == 4096
        assert parse_offset("0") == 0
        assert parse_offset("1440") == 1440
        assert parse_offset("12345") == 12345

    def test_parse_offset_hex_0x(self):
        """Hex with 0x prefix is parsed correctly."""
        parse_offset = self.get_parse_offset()
        assert parse_offset("0x1000") == 0x1000  # 4096
        assert parse_offset("0X1000") == 0x1000  # uppercase X
        assert parse_offset("0x5A0") == 0x5A0    # 1440
        assert parse_offset("0xFFFF") == 0xFFFF
        assert parse_offset("0x0") == 0

    def test_parse_offset_hex_h_suffix(self):
        """Hex with h suffix is parsed correctly."""
        parse_offset = self.get_parse_offset()
        assert parse_offset("1000h") == 0x1000  # 4096
        assert parse_offset("1000H") == 0x1000  # uppercase H
        assert parse_offset("5A0h") == 0x5A0    # 1440
        assert parse_offset("FFFFh") == 0xFFFF

    def test_parse_offset_whitespace_tolerance(self):
        """Leading/trailing whitespace is handled."""
        parse_offset = self.get_parse_offset()
        assert parse_offset("  4096  ") == 4096
        assert parse_offset(" 0x1000 ") == 0x1000
        assert parse_offset("\t1000h\n") == 0x1000

    def test_parse_offset_invalid_raises(self):
        """Invalid inputs raise BadParameter."""
        parse_offset = self.get_parse_offset()

        with pytest.raises(typer.BadParameter):
            parse_offset("not_a_number")

        with pytest.raises(typer.BadParameter):
            parse_offset("0xZZZZ")  # invalid hex

        with pytest.raises(typer.BadParameter):
            parse_offset("12.34")  # float

        # Note: negative numbers like "-100" will parse as int(-100)
        # which is technically valid. If we wanted to reject negatives,
        # we would need explicit validation in parse_offset.


class TestParseBitmapFormat:
    """Test bitmap format parsing with aliases."""

    def get_parse_bitmap_format(self):
        """Import parse_bitmap_format from cli module."""
        from baofeng_logo_flasher.cli import parse_bitmap_format
        return parse_bitmap_format

    def test_parse_canonical_names(self):
        """Canonical enum names are parsed correctly."""
        parse_format = self.get_parse_bitmap_format()

        assert parse_format("ROW_MAJOR_MSB") == BitmapFormat.ROW_MAJOR_MSB
        assert parse_format("ROW_MAJOR_LSB") == BitmapFormat.ROW_MAJOR_LSB
        assert parse_format("PAGE_MAJOR_MSB") == BitmapFormat.PAGE_MAJOR_MSB
        assert parse_format("PAGE_MAJOR_LSB") == BitmapFormat.PAGE_MAJOR_LSB

    def test_parse_canonical_lowercase(self):
        """Canonical names work regardless of case."""
        parse_format = self.get_parse_bitmap_format()

        assert parse_format("row_major_msb") == BitmapFormat.ROW_MAJOR_MSB
        assert parse_format("Row_Major_Lsb") == BitmapFormat.ROW_MAJOR_LSB

    def test_parse_short_aliases(self):
        """Short aliases (enum values) are parsed correctly."""
        parse_format = self.get_parse_bitmap_format()

        assert parse_format("row_msb") == BitmapFormat.ROW_MAJOR_MSB
        assert parse_format("row_lsb") == BitmapFormat.ROW_MAJOR_LSB
        assert parse_format("page_msb") == BitmapFormat.PAGE_MAJOR_MSB
        assert parse_format("page_lsb") == BitmapFormat.PAGE_MAJOR_LSB

    def test_parse_hyphenated_aliases(self):
        """Hyphenated versions work too."""
        parse_format = self.get_parse_bitmap_format()

        assert parse_format("row-major-msb") == BitmapFormat.ROW_MAJOR_MSB
        assert parse_format("row-msb") == BitmapFormat.ROW_MAJOR_MSB
        assert parse_format("page-major-lsb") == BitmapFormat.PAGE_MAJOR_LSB

    def test_parse_case_insensitive(self):
        """All formats are case-insensitive."""
        parse_format = self.get_parse_bitmap_format()

        assert parse_format("ROW_MSB") == BitmapFormat.ROW_MAJOR_MSB
        assert parse_format("Row_Msb") == BitmapFormat.ROW_MAJOR_MSB
        assert parse_format("PAGE_LSB") == BitmapFormat.PAGE_MAJOR_LSB

    def test_parse_whitespace_tolerance(self):
        """Leading/trailing whitespace is handled."""
        parse_format = self.get_parse_bitmap_format()

        assert parse_format("  row_msb  ") == BitmapFormat.ROW_MAJOR_MSB
        assert parse_format("\tpage_lsb\n") == BitmapFormat.PAGE_MAJOR_LSB

    def test_parse_invalid_raises(self):
        """Invalid formats raise BadParameter."""
        parse_format = self.get_parse_bitmap_format()

        with pytest.raises(typer.BadParameter):
            parse_format("invalid_format")

        with pytest.raises(typer.BadParameter):
            parse_format("msb_row")  # wrong order

        with pytest.raises(typer.BadParameter):
            parse_format("")


class TestVerifyCloneAlignment:
    """Test that verify_clone correctly handles 8-byte ident prefix."""

    def test_verify_clone_uses_correct_offset(self):
        """
        Regression test: verify_clone must add 8 to image offset.

        Clone image layout:
            Bytes 0-7:   8-byte ident (radio ID)
            Bytes 8+:    Memory dump starting at address 0x0000

        So radio address 0x0000 corresponds to image byte 8.
        """
        from baofeng_logo_flasher.protocol.uv5rm_protocol import UV5RMProtocol

        # Create a mock transport
        mock_transport = MagicMock()

        # Create protocol instance
        protocol = UV5RMProtocol(mock_transport)

        # Create test image data:
        # - 8 bytes of ident prefix
        # - followed by "memory" data
        ident = b"\x50\xBB\xFF\x01\x25\x98\x4D\x00"
        memory_at_0x0000 = b"RADIO_DATA_AT_ADDR_0000" + b"\x00" * 41  # 0x40 bytes

        # Image has ident + memory
        image_data = ident + memory_at_0x0000 + b"\x00" * 0x2000  # pad to expected size

        # Mock transport.read_block to return the memory data (no ident)
        # This simulates what the radio would return for address 0x0000
        mock_transport.read_block.return_value = memory_at_0x0000

        # Verify a small range
        result = protocol.verify_clone(image_data, ranges=[(0x0000, 0x0040)])

        # Should pass because:
        # - radio returns memory_at_0x0000 for address 0x0000
        # - image_data[0x0000 + 8] = image_data[8] = memory_at_0x0000
        assert result['verified'] is True
        assert result['errors'] == []
        assert result['checked_bytes'] == 0x40

    def test_verify_clone_detects_mismatch(self):
        """Mismatched data should be detected."""
        from baofeng_logo_flasher.protocol.uv5rm_protocol import UV5RMProtocol

        mock_transport = MagicMock()
        protocol = UV5RMProtocol(mock_transport)

        # Image data (with ident prefix)
        ident = b"\x50\xBB\xFF\x01\x25\x98\x4D\x00"
        memory_in_image = b"IMAGE_DATA" + b"\x00" * 54  # 0x40 bytes
        image_data = ident + memory_in_image + b"\x00" * 0x2000

        # Radio returns DIFFERENT data
        radio_data = b"DIFFERENT_DATA" + b"\x00" * 50  # 0x40 bytes
        mock_transport.read_block.return_value = radio_data

        result = protocol.verify_clone(image_data, ranges=[(0x0000, 0x0040)])

        # Should fail - data doesn't match
        assert result['verified'] is False
        assert len(result['errors']) == 1
        assert result['errors'][0]['address'] == 0x0000

    def test_verify_clone_without_offset_fix_would_fail(self):
        """
        This test demonstrates what would go wrong WITHOUT the +8 offset fix.

        If we compared radio addr 0 with image[0] (instead of image[8]),
        we'd be comparing memory data with the ident prefix, causing false failures.
        """
        from baofeng_logo_flasher.protocol.uv5rm_protocol import UV5RMProtocol

        mock_transport = MagicMock()
        protocol = UV5RMProtocol(mock_transport)

        # Create image where ident != memory data
        ident = b"\x50\xBB\xFF\x01\x25\x98\x4D\x00"
        memory_data = b"MEMORY_AT_0000" + b"\xFF" * 50  # 0x40 bytes - DIFFERENT from ident
        image_data = ident + memory_data + b"\x00" * 0x2000

        # Radio returns the memory data (correctly)
        mock_transport.read_block.return_value = memory_data

        # With correct +8 offset: image[8:] = memory_data -> MATCH
        result = protocol.verify_clone(image_data, ranges=[(0x0000, 0x0040)])

        # This should pass with the fix
        assert result['verified'] is True

        # Note: Before the fix, this would have compared:
        # radio_data = memory_data vs image[0:0x40] which starts with ident
        # That would have been a FALSE MISMATCH

