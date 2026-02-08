"""Tests for boot logo flasher module."""

import tempfile
from pathlib import Path
from PIL import Image

from baofeng_logo_flasher.boot_logo import (
    SERIAL_FLASH_CONFIGS,
    BootLogoError,
    baofeng_encrypt,
    convert_bmp_to_raw,
    flash_logo,
    read_logo,
)


def _make_bmp(tmp_path, size=(160, 128)) -> str:
    """Create a temporary BMP file."""
    img = Image.new("RGB", size, color=(10, 20, 30))
    path = tmp_path / "logo.bmp"
    img.save(path, format="BMP")
    return str(path)


class TestEncryption:
    """Test Baofeng encryption."""

    def test_encrypt_length_stable(self):
        """Encrypted output should match input length."""
        data = b"\x01\x02\x03\x04\x05"
        out = baofeng_encrypt(data, key=b"\xAB")
        assert len(out) == len(data)

    def test_encrypt_not_identity(self):
        """Encryption should change the data."""
        data = b"\x00\x00\x00\x00"
        out = baofeng_encrypt(data, key=b"\xAB\xCD")
        assert out != data

    def test_encrypt_deterministic(self):
        """Same input should produce same output."""
        data = b"test data"
        out1 = baofeng_encrypt(data)
        out2 = baofeng_encrypt(data)
        assert out1 == out2


class TestBMPConversion:
    """Test BMP to raw conversion."""

    def test_convert_bmp_rgb_unencrypted(self):
        """Convert BMP to RGB raw (no encryption)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            bmp_path = _make_bmp(tmp_path, size=(160, 128))
            # Use legacy config for RGB mode
            config = {
                "size": (160, 128),
                "color_mode": "RGB",
                "encrypt": False,
            }

            raw = convert_bmp_to_raw(bmp_path, config)

            # 160 * 128 * 3 bytes for RGB
            assert len(raw) == 160 * 128 * 3

    def test_convert_bmp_encrypted(self):
        """Convert BMP to raw with encryption."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            bmp_path = _make_bmp(tmp_path, size=(160, 128))
            # Use explicit config for encrypted RGB mode
            config = {
                "size": (160, 128),
                "color_mode": "RGB",
                "encrypt": True,
            }

            raw = convert_bmp_to_raw(bmp_path, config)

            # 160 * 128 * 3 bytes for RGB (encrypted)
            assert len(raw) == 160 * 128 * 3

    def test_convert_bmp_resize(self):
        """BMP should be resized to target dimensions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            # Create image with wrong size
            img = Image.new("RGB", (80, 64), color=(10, 20, 30))
            path = tmp_path / "wrong_size.bmp"
            img.save(path, format="BMP")

            config = {
                "size": (160, 128),
                "color_mode": "RGB",
                "encrypt": False,
            }

            raw = convert_bmp_to_raw(str(path), config)

            # Should still be correct size after resize
            assert len(raw) == 160 * 128 * 3


class TestFlashSimulation:
    """Test flash operation in simulation mode."""

    def test_flash_simulate(self):
        """Simulation mode should not require actual serial."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            bmp_path = _make_bmp(tmp_path, size=(160, 128))

            result = flash_logo(
                port="SIMULATED",
                bmp_path=bmp_path,
                config=dict(SERIAL_FLASH_CONFIGS["UV-5RM"]),
                simulate=True,
            )

            assert "Simulation" in result
            # New A5 protocol simulation message format
            assert "RGB565" in result or "A5" in result or "160x128" in result


class TestModelConfigs:
    """Test model configurations."""

    def test_uv5rm_config_exists(self):
        """UV-5RM should be in configs."""
        assert "UV-5RM" in SERIAL_FLASH_CONFIGS
        config = SERIAL_FLASH_CONFIGS["UV-5RM"]
        assert config["size"] == (160, 128)
        # New A5 protocol uses 'protocol' key instead of 'encrypt'
        assert config.get("protocol") == "a5_logo"
        assert config.get("color_mode") == "RGB565"
        assert config.get("write_addr_mode") == "chunk"

    def test_dm32uv_config_exists(self):
        """DM-32UV should be in configs."""
        assert "DM-32UV" in SERIAL_FLASH_CONFIGS
        config = SERIAL_FLASH_CONFIGS["DM-32UV"]
        assert config["size"] == (240, 320)
        assert config["encrypt"] is False


class TestRGB565Conversion:
    """Test RGB565 color format conversion."""

    def test_convert_rgb565_size(self):
        """RGB565 output should be 2 bytes per pixel."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            bmp_path = _make_bmp(tmp_path, size=(160, 128))
            config = {
                "size": (160, 128),
                "color_mode": "RGB565",
            }

            raw = convert_bmp_to_raw(bmp_path, config)

            # 160 * 128 * 2 bytes for RGB565
            assert len(raw) == 160 * 128 * 2

    def test_convert_rgb565_format(self):
        """RGB565 should use little-endian byte order."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            # Create single red pixel image
            img = Image.new("RGB", (1, 1), color=(255, 0, 0))  # Pure red
            path = tmp_path / "red.bmp"
            img.save(path, format="BMP")

            config = {
                "size": (1, 1),
                "color_mode": "RGB565",
            }

            raw = convert_bmp_to_raw(str(path), config)

            # Pure red in RGB565: 11111 000000 00000 = 0xF800
            # Little-endian: 0x00, 0xF8
            assert len(raw) == 2
            assert raw[0] == 0x00
            assert raw[1] == 0xF8


class TestA5Protocol:
    """Test A5 protocol configuration."""

    def test_uv17pro_has_a5_protocol(self):
        """UV-17Pro should also use A5 protocol."""
        assert "UV-17Pro" in SERIAL_FLASH_CONFIGS
        config = SERIAL_FLASH_CONFIGS["UV-17Pro"]
        assert config.get("protocol") == "a5_logo"
        assert config.get("baudrate") == 115200
        assert config.get("chunk_size") == 1024
        assert config.get("write_addr_mode") == "chunk"

    def test_uv17r_has_a5_protocol(self):
        """UV-17R should also use A5 protocol."""
        assert "UV-17R" in SERIAL_FLASH_CONFIGS
        config = SERIAL_FLASH_CONFIGS["UV-17R"]
        assert config.get("protocol") == "a5_logo"
        assert config.get("write_addr_mode") == "chunk"


class TestReadLogoSupport:
    """Test read-logo support boundaries."""

    def test_read_logo_rejects_a5_models(self):
        """A5 direct logo protocol currently supports upload, not read-back."""
        config = dict(SERIAL_FLASH_CONFIGS["UV-5RM"])
        try:
            read_logo("SIMULATED", config, simulate=True)
            assert False, "Expected BootLogoError for A5 read_logo"
        except BootLogoError as exc:
            assert "not implemented" in str(exc).lower()
