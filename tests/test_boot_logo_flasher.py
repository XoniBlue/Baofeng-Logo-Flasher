"""Tests for A5-only boot logo flasher module."""

import tempfile
from pathlib import Path

from PIL import Image

from baofeng_logo_flasher.boot_logo import (
    SERIAL_FLASH_CONFIGS,
    BootLogoError,
    flash_logo,
    read_radio_id,
)


def _make_image(tmp_path: Path, size=(160, 128)) -> str:
    """Create a temporary image file."""
    img = Image.new("RGB", size, color=(10, 20, 30))
    path = tmp_path / "logo.png"
    img.save(path)
    return str(path)


class TestA5ModelConfigs:
    """Test A5 model configuration set."""

    def test_only_a5_models_are_present(self):
        """Serial flash configs should only include supported A5 models."""
        expected = {"UV-5RM", "UV-17Pro", "UV-17R"}
        assert set(SERIAL_FLASH_CONFIGS.keys()) == expected

    def test_all_models_use_a5_protocol(self):
        """Every serial config should be A5 protocol with chunk addressing."""
        for cfg in SERIAL_FLASH_CONFIGS.values():
            assert cfg.get("protocol") == "a5_logo"
            assert cfg.get("write_addr_mode") == "chunk"
            assert cfg.get("chunk_size") == 1024
            assert cfg.get("pixel_order") == "rgb"


class TestFlashSimulation:
    """Test flash operation in simulation mode."""

    def test_flash_simulate_a5(self):
        """Simulation mode should report A5 upload details."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            image_path = _make_image(tmp_path)

            result = flash_logo(
                port="SIMULATED",
                bmp_path=image_path,
                config=dict(SERIAL_FLASH_CONFIGS["UV-5RM"]),
                simulate=True,
            )

            assert "Simulation" in result
            assert "A5" in result or "RGB565" in result or "160x128" in result

    def test_flash_rejects_non_a5_protocol(self):
        """Legacy/non-A5 protocol configs should be rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            image_path = _make_image(tmp_path)

            bad_cfg = dict(SERIAL_FLASH_CONFIGS["UV-5RM"])
            bad_cfg["protocol"] = "legacy"

            try:
                flash_logo(
                    port="SIMULATED",
                    bmp_path=image_path,
                    config=bad_cfg,
                    simulate=True,
                )
                assert False, "Expected BootLogoError for non-A5 protocol"
            except BootLogoError as exc:
                assert "only a5" in str(exc).lower() or "unsupported protocol" in str(exc).lower()


class TestReadRadioId:
    """Test protocol constraints for read_radio_id."""

    def test_read_radio_id_rejects_non_uv17pro(self):
        """A5 build should reject uv5r protocol mode early."""
        try:
            read_radio_id("SIMULATED", protocol="uv5r")
            assert False, "Expected BootLogoError for unsupported protocol"
        except BootLogoError as exc:
            assert "unsupported protocol" in str(exc).lower()
