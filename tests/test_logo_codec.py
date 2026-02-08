"""Test suite for logo codec and patcher."""

import tempfile
from pathlib import Path
from PIL import Image

import pytest

from baofeng_logo_flasher.logo_codec import LogoCodec, BitmapFormat
from baofeng_logo_flasher.logo_patcher import LogoPatcher


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


class TestLogoPatcher:
    """Tests for logo patching."""

    @pytest.fixture
    def temp_image(self):
        """Create temporary test image file."""
        with tempfile.NamedTemporaryFile(suffix='.img', delete=False) as f:
            # Create a 64KB test image
            f.write(b'\xFF' * 65536)
            temp_path = f.name

        yield temp_path

        # Cleanup
        Path(temp_path).unlink(missing_ok=True)

    def test_backup_region(self, temp_image):
        """Test backing up image region."""
        patcher = LogoPatcher()

        backup_info = patcher.backup_region(temp_image, 0x1000, 256)

        assert backup_info['offset'] == 0x1000
        assert backup_info['length'] == 256
        assert 'hash' in backup_info
        assert 'data' in backup_info
        assert len(backup_info['data']) == 256

    def test_patch_image(self, temp_image):
        """Test patching image."""
        patcher = LogoPatcher()

        # Create logo data to patch
        logo_data = b'\x42' * 256

        result = patcher.patch_image(temp_image, 0x1000, logo_data)

        assert result['offset'] == 0x1000
        assert result['length'] == 256
        assert result['verified'] == True

        # Verify patch was written
        with open(temp_image, 'rb') as f:
            f.seek(0x1000)
            readback = f.read(256)
            assert readback == logo_data

    def test_restore_region(self, temp_image):
        """Test restoring backed-up region."""
        patcher = LogoPatcher()

        # Backup original
        backup_info = patcher.backup_region(temp_image, 0x1000, 256)
        original_data = backup_info['data']

        # Patch with different data
        new_data = b'\x42' * 256
        patcher.patch_image(temp_image, 0x1000, new_data, verify=True)

        # Verify patch
        with open(temp_image, 'rb') as f:
            f.seek(0x1000)
            readback = f.read(256)
            assert readback == new_data

        # Restore
        patcher.restore_region(temp_image, backup_info)

        # Verify restore
        with open(temp_image, 'rb') as f:
            f.seek(0x1000)
            readback = f.read(256)
            assert readback == original_data

    def test_bounds_checking(self, temp_image):
        """Test that patcher checks bounds."""
        patcher = LogoPatcher()

        # Try to write past end of file
        with pytest.raises(ValueError):
            patcher.patch_image(temp_image, 65000, b'x' * 1024)

    def test_backup_creates_files(self, temp_image):
        """Test that backups are saved to disk."""
        patcher = LogoPatcher()

        backup_info = patcher.backup_region(temp_image, 0x1000, 256)
        backup_path = Path(backup_info['path'])

        assert backup_path.exists()
        assert backup_path.stat().st_size == 256


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
