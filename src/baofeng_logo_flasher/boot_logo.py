"""A5 boot logo flashing support for Baofeng UV-5RM / UV-17 family."""

from typing import Dict, List, Optional, Callable
import logging

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    serial = None

# Import model registry for runtime configuration.
from .models import (
    get_model as registry_get_model,
    get_serial_flash_config as registry_get_flash_config,
    list_models as registry_list_models,
)

logger = logging.getLogger(__name__)

BOOT_LOGO_SIZE = (160, 128)


class BootLogoError(Exception):
    """Errors raised by boot logo operations."""


def _build_serial_flash_configs() -> Dict[str, Dict]:
    """Build A5 serial flash configs from registry."""
    result: Dict[str, Dict] = {}
    for name in registry_list_models():
        reg_model = registry_get_model(name)
        if reg_model is None or not reg_model.logo_regions:
            continue

        # A5 logo uploader only supports UV17Pro-family protocol.
        protocol_name = getattr(reg_model.protocol, "value", "").lower()
        if protocol_name != "uv17pro":
            continue

        cfg = registry_get_flash_config(name)
        if not cfg:
            continue

        normalized = dict(cfg)
        normalized.update(
            {
                "protocol": "a5_logo",
                "write_addr_mode": "chunk",
                "chunk_size": 1024,
                "pixel_order": "rgb",
                "handshake": b"PROGRAMBFNORMALU",
                "handshake_ack": b"\x06",
            }
        )

        required = ("size", "color_mode", "start_addr", "baudrate", "timeout", "protocol")
        missing = [k for k in required if k not in normalized]
        if missing:
            raise RuntimeError(
                f"Registry-derived serial config for '{name}' missing keys: {', '.join(missing)}"
            )

        result[name] = normalized

    required_models = ("UV-5RM", "UV-17Pro", "UV-17R")
    for model_name in required_models:
        if model_name not in result:
            raise RuntimeError(
                f"Required A5 model missing from registry-derived configs: {model_name}"
            )

    return result


SERIAL_FLASH_CONFIGS: Dict[str, Dict] = _build_serial_flash_configs()


def list_serial_ports() -> List[str]:
    """List available serial ports."""
    if not serial:
        return []
    return [p.device for p in serial.tools.list_ports.comports()]


def read_radio_id(
    port: str,
    magic: bytes = None,
    baudrate: int = 115200,
    timeout: float = 1.5,
    protocol: str = "uv17pro",
    post_ident_magics: list = None,
    fingerprint: bytes = b"\x06",
) -> str:
    """
    Connect to radio and read its ID using UV17Pro-compatible handshake.
    """
    if not serial:
        raise BootLogoError("PySerial not installed")

    if protocol != "uv17pro":
        raise BootLogoError(
            "Unsupported protocol for this build. "
            "A5 logo flasher only supports uv17pro-family models."
        )

    # Default magic for UV-5RM/UV-17 family.
    if magic is None:
        magic = b"PROGRAMBFNORMALU"

    return _do_ident_uv17pro(port, magic, baudrate, timeout, post_ident_magics, fingerprint)


def _do_ident_uv17pro(
    port: str,
    magic: bytes,
    baudrate: int,
    timeout: float,
    post_ident_magics: list = None,
    fingerprint: bytes = b"\x06",
) -> str:
    """
    Perform identification handshake using UV17Pro protocol.
    """
    ser = serial.Serial(
        port=port,
        baudrate=baudrate,
        bytesize=8,
        parity="N",
        stopbits=1,
        timeout=timeout,
        write_timeout=timeout,
    )

    try:
        # Clean buffer first.
        ser.timeout = 0.005
        _ = ser.read(256)
        ser.timeout = timeout

        logger.debug("Connected to %s at %d baud (UV17Pro protocol)", port, baudrate)

        # Send the full magic string at once.
        ser.write(magic)

        # Read expected fingerprint response.
        fingerprint_len = len(fingerprint)
        response = ser.read(fingerprint_len)

        if not response:
            raise BootLogoError("No response to ident magic. Is radio powered on and connected?")

        if not response.startswith(fingerprint):
            raise BootLogoError(
                f"Unexpected response: {response.hex()} (expected {fingerprint.hex()})"
            )

        # Send additional magic commands when provided.
        model_name = None
        if post_ident_magics:
            for i, (cmd, resp_len) in enumerate(post_ident_magics):
                ser.write(cmd)
                resp = ser.read(resp_len)
                if i == 1 and resp:
                    try:
                        model_name = resp.decode("ascii", errors="ignore").strip()
                    except Exception:
                        pass

        if model_name:
            return f"UV17Pro ({model_name})"
        return f"UV17Pro-{response.hex().upper()}"
    finally:
        ser.close()


def flash_logo(
    port: str,
    bmp_path: str,
    config: Dict,
    simulate: bool = False,
    progress_cb: Optional[Callable[[int, int], None]] = None,
    debug_bytes: bool = False,
    debug_output_dir: Optional[str] = None,
    write_address_mode: Optional[str] = None,
) -> str:
    """
    Flash boot logo using the A5 framing protocol.
    """
    if not serial and not simulate:
        raise BootLogoError("PySerial not installed")

    protocol_type = config.get("protocol", "")
    if protocol_type != "a5_logo":
        raise BootLogoError(
            "Unsupported protocol for this build. "
            "Only A5 logo upload is available."
        )

    effective_write_address_mode = write_address_mode or config.get("write_addr_mode", "chunk")
    return _flash_logo_a5_protocol(
        port,
        bmp_path,
        config,
        simulate,
        progress_cb,
        debug_bytes=debug_bytes,
        debug_output_dir=debug_output_dir,
        write_address_mode=effective_write_address_mode,
    )


def _flash_logo_a5_protocol(
    port: str,
    bmp_path: str,
    config: Dict,
    simulate: bool = False,
    progress_cb: Optional[Callable[[int, int], None]] = None,
    debug_bytes: bool = False,
    debug_output_dir: Optional[str] = None,
    write_address_mode: str = "chunk",
) -> str:
    """
    Flash logo using the A5 framing protocol for UV-5RM/UV-17 family.
    """
    from .protocol.logo_protocol import upload_logo as protocol_upload_logo

    if simulate:
        from PIL import Image

        try:
            img = Image.open(bmp_path)
            return (
                f"Simulation: Would upload {img.size[0]}x{img.size[1]} image "
                f"to {port} as 160x128 RGB565 using A5 logo protocol"
            )
        except Exception as e:
            return f"Simulation: Would upload image to {port} (could not read: {e})"

    logger.info("Flashing logo using A5 protocol to %s", port)
    pixel_order = str(config.get("pixel_order", "rgb")).lower()
    if pixel_order not in {"rgb", "bgr"}:
        raise BootLogoError(f"Invalid pixel_order in config: {pixel_order}")

    return protocol_upload_logo(
        port,
        bmp_path,
        progress_cb,
        simulate=False,
        debug_bytes=debug_bytes,
        debug_output_dir=debug_output_dir,
        address_mode=write_address_mode,
        pixel_order=pixel_order,
    )
