"""
Core workflow actions for Baofeng Logo Flasher.

This module exposes pure-ish functions that both CLI and Streamlit can call.
All write operations go through the safety context for gating.
"""

import hashlib
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, Callable

from .results import OperationResult
from .safety import SafetyContext, require_write_permission, WritePermissionError
from .parsing import parse_bitmap_format

logger = logging.getLogger(__name__)


class _ListLogHandler(logging.Handler):
    """Capture log records into a list of formatted strings."""

    def __init__(self, level: int = logging.INFO) -> None:
        super().__init__(level)
        self.records = []
        self.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(self.format(record))


@contextmanager
def _capture_logs(logger_name: str = "baofeng_logo_flasher"):
    """Capture logs for core operations into a list."""
    target_logger = logging.getLogger(logger_name)
    handler = _ListLogHandler()
    previous_level = target_logger.level
    if previous_level in (logging.NOTSET, logging.WARNING, logging.ERROR, logging.CRITICAL):
        target_logger.setLevel(logging.INFO)
    target_logger.addHandler(handler)
    try:
        yield handler.records
    finally:
        target_logger.removeHandler(handler)
        target_logger.setLevel(previous_level)


def prepare_logo_bytes(
    input_image_path: str,
    target_size: Tuple[int, int] = (128, 64),
    bitmap_format: str = "row_msb",
    dither: bool = False,
) -> Tuple[bytes, Dict[str, Any]]:
    """
    Convert input image to logo bytes suitable for radio.

    Args:
        input_image_path: Path to input image (PNG, JPG, BMP, etc.)
        target_size: Target dimensions (width, height)
        bitmap_format: Bitmap format string (row_msb, page_lsb, etc.)
        dither: Whether to apply dithering for monochrome conversion

    Returns:
        Tuple of (logo_bytes, metadata_dict)

        metadata contains:
            - original_size: (width, height)
            - target_size: (width, height)
            - format: parsed BitmapFormat value
            - bytes_len: length of output
            - sha256: hash of output bytes

    Raises:
        ValueError: If format is invalid
        FileNotFoundError: If input file doesn't exist
    """
    from baofeng_logo_flasher.utils.logo_codec import LogoCodec

    path = Path(input_image_path)
    if not path.exists():
        raise FileNotFoundError(f"Input image not found: {input_image_path}")

    fmt = parse_bitmap_format(bitmap_format)
    codec = LogoCodec(fmt, dither=dither)

    # Get original size for metadata
    from PIL import Image
    with Image.open(input_image_path) as img:
        original_size = img.size

    logo_bytes = codec.convert_image(input_image_path, target_size)

    metadata = {
        "original_size": original_size,
        "target_size": target_size,
        "format": fmt.value,
        "bytes_len": len(logo_bytes),
        "sha256": hashlib.sha256(logo_bytes).hexdigest(),
    }

    return logo_bytes, metadata


def flash_logo_serial(
    port: str,
    bmp_path: str,
    config: Dict[str, Any],
    safety_ctx: SafetyContext,
    progress_cb: Optional[Callable[[int, int], None]] = None,
    debug_bytes: bool = False,
    debug_output_dir: Optional[str] = None,
    write_address_mode: Optional[str] = None,
) -> OperationResult:
    """
    Flash boot logo via direct serial protocol (UV-5RM style).

    This wraps the boot_logo.flash_logo function with safety gating.

    Args:
        port: Serial port path
        bmp_path: Path to BMP file
        config: Model config dict from SERIAL_FLASH_CONFIGS
        safety_ctx: Safety context for gating
        progress_cb: Optional progress callback
        debug_bytes: If True, dump protocol payload/frame artifacts
        debug_output_dir: Directory for debug artifact dumps
        write_address_mode: CMD_WRITE address semantics ("byte" or "chunk").
            If None, model config decides (recommended).

    Returns:
        OperationResult with flash status
    """
    if not Path(bmp_path).exists():
        return OperationResult.failure(
            operation="flash_logo_serial",
            error=f"BMP file not found: {bmp_path}",
        )

    start_addr = config.get("start_addr", 0)
    target_region = f"Serial flash at 0x{start_addr:04X}"

    with _capture_logs() as logs:
        # Enforce safety
        require_write_permission(
            safety_ctx,
            target_region=target_region,
            bytes_length=config["size"][0] * config["size"][1] * 2,  # RGB565 payload size
            offset=start_addr,
        )

        try:
            from baofeng_logo_flasher.core.boot_logo import flash_logo as _flash_logo_impl

            result_str = _flash_logo_impl(
                port=port,
                bmp_path=bmp_path,
                config=config,
                simulate=safety_ctx.simulate,
                progress_cb=progress_cb,
                debug_bytes=debug_bytes,
                debug_output_dir=debug_output_dir,
                write_address_mode=write_address_mode,
            )

            result = OperationResult.success(
                operation="flash_logo_serial",
                model=safety_ctx.model_detected,
                region=target_region,
            )
            result.metadata["result_message"] = result_str
            result.logs = logs

            if safety_ctx.simulate:
                result.metadata["simulated"] = True
                result.add_warning("Simulation mode - no actual write performed")

            return result

        except WritePermissionError:
            raise
        except Exception as e:
            logger.exception("flash_logo_serial failed")
            result = OperationResult.failure(
                operation="flash_logo_serial",
                error=str(e),
                model=safety_ctx.model_detected,
            )
            result.logs = logs
            return result
