"""Test suite for logo codec."""

from PIL import Image

import pytest

from baofeng_logo_flasher.logo_codec import LogoCodec, BitmapFormat


class TestLogoCodec:
    """Tests for image encoding/decoding."""

    @pytest.fixture
    def test_image_128x64(self):
        """Create a simple 128x64 test image."""
        img = Image.new('1', (128, 64), 1)
        pixels = img.load()

        # Draw a simple pattern (checkerboard)
        for y in range(64):
            for x in range(128):
                if (x + y) % 2 == 0:
                    pixels[x, y] = 0

        return img

    def test_pack_row_msb(self, test_image_128x64):
        """Test row-major MSB packing."""
        codec = LogoCodec(BitmapFormat.ROW_MAJOR_MSB)
        data = codec.pack(test_image_128x64)

        # 128 pixels per row = 16 bytes
        # 64 rows = 1024 bytes
        assert len(data) == 1024
        assert isinstance(data, bytes)

    def test_pack_row_lsb(self, test_image_128x64):
        """Test row-major LSB packing."""
        codec = LogoCodec(BitmapFormat.ROW_MAJOR_LSB)
        data = codec.pack(test_image_128x64)
        assert len(data) == 1024

    def test_pack_page_msb(self, test_image_128x64):
        """Test page-major MSB packing."""
        codec = LogoCodec(BitmapFormat.PAGE_MAJOR_MSB)
        data = codec.pack(test_image_128x64)
        # 64 height = 8 pages, 128 width = 128 bytes per page
        assert len(data) == 1024

    def test_pack_page_lsb(self, test_image_128x64):
        """Test page-major LSB packing."""
        codec = LogoCodec(BitmapFormat.PAGE_MAJOR_LSB)
        data = codec.pack(test_image_128x64)
        assert len(data) == 1024

    def test_unpack_row_msb(self):
        """Test row-major MSB unpacking."""
        codec = LogoCodec(BitmapFormat.ROW_MAJOR_MSB)

        # Create test data
        data = bytes(1024)  # All zeros (all black)

        img = codec.unpack(data, 128, 64)
        assert img.size == (128, 64)
        assert img.mode == '1'

    def test_roundtrip_row_msb(self, test_image_128x64):
        """Test pack/unpack roundtrip for row-major MSB."""
        codec = LogoCodec(BitmapFormat.ROW_MAJOR_MSB)

        # Pack
        packed = codec.pack(test_image_128x64)

        # Unpack
        unpacked = codec.unpack(packed, 128, 64)

        # Verify
        assert unpacked.size == test_image_128x64.size
        assert unpacked.mode == '1'

        # Pixel-by-pixel comparison
        orig_pixels = test_image_128x64.load()
        unpacked_pixels = unpacked.load()

        for y in range(64):
            for x in range(128):
                assert orig_pixels[x, y] == unpacked_pixels[x, y]

    def test_roundtrip_all_formats(self, test_image_128x64):
        """Test roundtrip for all formats."""
        for fmt in BitmapFormat:
            codec = LogoCodec(fmt)

            packed = codec.pack(test_image_128x64)
            unpacked = codec.unpack(packed, 128, 64)

            # Verify dimensions
            assert unpacked.size == (128, 64)

            # Verify pixels match
            orig_pixels = test_image_128x64.load()
            unpacked_pixels = unpacked.load()

            match_count = 0
            for y in range(64):
                for x in range(128):
                    if orig_pixels[x, y] == unpacked_pixels[x, y]:
                        match_count += 1

            # Should have 100% match
            assert match_count == 128 * 64, f"Format {fmt}: pixel mismatch"

    def test_resize_image(self):
        """Test image resizing."""
        codec = LogoCodec()

        # Create 256x256 image
        large = Image.new('RGB', (256, 256), 'white')

        resized = codec.resize_image(large, (128, 64))
        assert resized.size == (128, 64)

    def test_to_monochrome(self):
        """Test RGB to monochrome conversion."""
        codec = LogoCodec()

        # Create RGB image with gradient
        img = Image.new('RGB', (128, 64), (128, 128, 128))

        mono = codec.to_monochrome(img)
        assert mono.mode == '1'
        assert mono.size == (128, 64)

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
