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
    from baofeng_logo_flasher.logo_codec import LogoCodec

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


def read_clone(
    port: str,
    baud: int = 115200,
    timeout: float = 3.0,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> OperationResult:
    """
    Download clone data from radio.

    Args:
        port: Serial port path
        baud: Baud rate (default 115200 for UV17Pro protocol)
        timeout: Read timeout in seconds
        progress_cb: Optional progress callback(bytes_read, total)

    Returns:
        OperationResult with:
            - ok: True if successful
            - metadata["clone_data"]: bytes of clone data
            - metadata["ident"]: identification result dict
            - model: detected model name
            - bytes_len: size of clone
            - hashes["sha256"]: hash of clone data
    """
    with _capture_logs() as logs:
        try:
            from baofeng_logo_flasher.protocol import UV5RMTransport, UV5RMProtocol

            transport = UV5RMTransport(port, baudrate=baud, timeout=timeout)
            transport.open()

            try:
                protocol = UV5RMProtocol(transport)
                ident_result = protocol.identify_radio()
                clone_data = protocol.download_clone(progress_cb=progress_cb)

                model = ident_result.get("model", "Unknown")

                result = OperationResult.success(
                    operation="read_clone",
                    model=model,
                    bytes_len=len(clone_data),
                )
                result.hashes["sha256"] = hashlib.sha256(clone_data).hexdigest()
                result.metadata["clone_data"] = clone_data
                result.metadata["ident"] = ident_result
                result.logs = logs

                # Add warning if model is unknown
                if model == "Unknown" or not model:
                    result.add_warning("Model could not be identified")

                return result

            finally:
                transport.close()

        except Exception as e:
            logger.exception("read_clone failed")
            result = OperationResult.failure(
                operation="read_clone",
                error=str(e),
            )
            result.logs = logs
            return result


def write_logo(
    port: str,
    logo_bytes: bytes,
    target_region_start: int,
    safety_ctx: SafetyContext,
    block_size: int = 64,
    baud: int = 115200,
    timeout: float = 3.0,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> OperationResult:
    """
    Write logo bytes to radio at specified address.

    This function uses the protocol's block write mechanism.
    Safety context is enforced before any write occurs.

    Args:
        port: Serial port path
        logo_bytes: Logo data to write
        target_region_start: Start address for write
        safety_ctx: Safety context for gating
        block_size: Block size for writes (default 64)
        baud: Baud rate
        timeout: Timeout in seconds
        progress_cb: Optional progress callback(written, total)

    Returns:
        OperationResult with write status

    Raises:
        WritePermissionError: If safety check fails
    """
    target_region = f"0x{target_region_start:06X}-0x{target_region_start + len(logo_bytes):06X}"

    with _capture_logs() as logs:
        # Enforce safety gate
        require_write_permission(
            safety_ctx,
            target_region=target_region,
            bytes_length=len(logo_bytes),
            offset=target_region_start,
        )

        # If simulation mode, return success without actual write
        if safety_ctx.simulate:
            result = OperationResult.success(
                operation="write_logo",
                model=safety_ctx.model_detected,
                region=target_region,
                bytes_len=len(logo_bytes),
            )
            result.metadata["simulated"] = True
            result.add_warning("Simulation mode - no actual write performed")
            result.logs = logs
            return result

        try:
            from baofeng_logo_flasher.protocol import UV5RMTransport, UV5RMProtocol

            transport = UV5RMTransport(port, baudrate=baud, timeout=timeout)
            transport.open()

            try:
                protocol = UV5RMProtocol(transport)
                ident_result = protocol.identify_radio()

                model = ident_result.get("model", safety_ctx.model_detected)
                if safety_ctx.is_model_unknown and model:
                    safety_ctx.model_detected = model

                # Write blocks
                total = len(logo_bytes)
                end = target_region_start + total
                offset = 0

                for addr in range(target_region_start, end, block_size):
                    size = min(block_size, end - addr)
                    chunk = logo_bytes[offset:offset + size]
                    protocol.write_block(addr, chunk)
                    offset += size
                    if progress_cb:
                        progress_cb(offset, total)

                # Verify by reading back
                readback = bytearray()
                for addr in range(target_region_start, end, block_size):
                    size = min(block_size, end - addr)
                    block = protocol.read_block(addr, size)
                    readback.extend(block)

                verified = bytes(readback) == logo_bytes

                result = OperationResult.success(
                    operation="write_logo",
                    model=model,
                    region=target_region,
                    bytes_len=len(logo_bytes),
                )
                result.hashes["sha256"] = hashlib.sha256(logo_bytes).hexdigest()
                result.metadata["verified"] = verified
                result.logs = logs

                if not verified:
                    result.add_error("Readback verification failed")

                return result

            finally:
                transport.close()

        except WritePermissionError:
            raise
        except Exception as e:
            logger.exception("write_logo failed")
            result = OperationResult.failure(
                operation="write_logo",
                error=str(e),
                model=safety_ctx.model_detected,
            )
            result.logs = logs
            return result


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
            from baofeng_logo_flasher.boot_logo import flash_logo as _flash_logo_impl

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
