"""Boot logo flashing support for Baofeng UV-5RM / UV-17 family and DM-32UV picture tool protocol."""

from typing import Dict, List, Optional, Callable
import logging

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    serial = None

# Import model registry for runtime configuration.
from ..models import (
    get_model as registry_get_model,
    get_serial_flash_config as registry_get_flash_config,
    list_models as registry_list_models,
)

logger = logging.getLogger(__name__)

BOOT_LOGO_SIZE = (160, 128)


class BootLogoError(Exception):
    """Errors raised by boot logo operations."""


def _build_serial_flash_configs() -> Dict[str, Dict]:
    """Build serial flash configs.

    Registry-derived A5 configs:
    - UV-5RM / UV-17 family (A5 framing protocol)

    Manually defined configs:
    - DM-32UV vendor PowerOnPicture protocol ("dm32uv_picture")
    """
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

    # DM-32UV "PowerOnPicture.exe" protocol (reverse engineered).
    # - Serial 115200 8N1, DTR/RTS on
    # - RGB565 payload, 240x320 for DM32 2-inch screen (per vendor readme)
    # - Uses 'W' packets with 24-bit address + 16-bit length, ACK=0x06
    #
    # Unknown:
    # - The vendor EXE uses a base address value for the 24-bit address field.
    #   We default base_addr=0; advanced users can change start_addr if needed.
    result["DM-32UV"] = {
        "size": (240, 320),
        "color_mode": "RGB565",
        "encrypt": False,
        "start_addr": 0x000000,  # Used as base_addr for W packets (24-bit)
        "baudrate": 115200,
        "timeout": 0.5,
        "protocol": "dm32uv_picture",
        "chunk_size": 0x1000,
        "ack_timeout": 5.0,
        "notes": [
            "Vendor protocol from PowerOnPicture.exe",
            "Writes RGB565 payload with 'W' packets (0x57) and 0x06 ACK",
            "BIN files contain an 8-byte header; on-wire skips the first 8 bytes",
        ],
    }

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
    Connect to radio and read an A5-family identification fingerprint.

    IMPORTANT:
    - This identifier is advisory and primarily proves protocol reachability.
    - UV-5RM and UV-17 variants may report overlapping UV17Pro-family strings.
    - Callers must not hard-block flashing based on this string alone.
      The effective safety boundary is protocol/profile compatibility.
    """
    if not serial:
        raise BootLogoError("PySerial not installed")

    if protocol == "dm32uv_picture":
        return _do_probe_dm32uv(port, baudrate=baudrate, timeout=timeout)
    if protocol != "uv17pro":
        raise BootLogoError(f"Unsupported protocol: {protocol}")

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
    if protocol_type not in {"a5_logo", "dm32uv_picture"}:
        raise BootLogoError(
            "Unsupported protocol for this build. "
            "Supported: a5_logo, dm32uv_picture."
        )

    if protocol_type == "a5_logo":
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

    return _flash_logo_dm32uv_picture_protocol(
        port,
        bmp_path,
        config,
        simulate,
        progress_cb,
    )


def _do_probe_dm32uv(port: str, *, baudrate: int = 115200, timeout: float = 0.5) -> str:
    """
    Minimal non-destructive reachability probe for DM-32UV.

    The vendor tool sends "PSEARCH" and expects an 0x06 ACK in the response buffer.
    We keep this probe lightweight and avoid entering PROGRAM mode.
    """
    if not serial:
        raise BootLogoError("PySerial not installed")

    ser = serial.Serial(
        port=port,
        baudrate=baudrate,
        bytesize=8,
        parity="N",
        stopbits=1,
        timeout=timeout,
        write_timeout=timeout,
        rtscts=False,
        dsrdtr=False,
    )
    try:
        ser.dtr = True
        ser.rts = True
        ser.reset_input_buffer()
        ser.reset_output_buffer()

        ser.write(b"PSEARCH")
        resp = ser.read(8)
        if not resp or resp[:1] != b"\x06":
            raise BootLogoError(f"DM32UV probe failed (resp={resp.hex() if resp else 'empty'})")
        return "DM32UV (PSEARCH ACK)"
    finally:
        ser.close()


def _flash_logo_dm32uv_picture_protocol(
    port: str,
    bmp_path: str,
    config: Dict,
    simulate: bool = False,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> str:
    """
    Flash logo using the DM-32UV vendor PowerOnPicture protocol.
    """
    if simulate:
        from PIL import Image

        try:
            img = Image.open(bmp_path)
            w, h = config.get("size", (240, 320))
            return (
                f"Simulation: Would upload {img.size[0]}x{img.size[1]} image "
                f"to {port} as {w}x{h} RGB565 using DM32UV picture protocol"
            )
        except Exception as e:
            return f"Simulation: Would upload image to {port} (could not read: {e})"

    from ..protocol.dm32uv_picture_protocol import (
        DM32UVPictureUploader,
        build_dm32uv_bin_from_image,
    )

    w, h = config.get("size", (240, 320))
    base_addr = int(config.get("start_addr", 0)) & 0xFFFFFF
    ack_timeout = float(config.get("ack_timeout", 5.0))

    bin_bytes = build_dm32uv_bin_from_image(bmp_path, size=(int(w), int(h)))

    with DM32UVPictureUploader(
        port=port,
        baudrate=int(config.get("baudrate", 115200)),
        timeout=float(config.get("timeout", 0.5)),
        ack_timeout=ack_timeout,
        base_addr=base_addr,
        chunk_size=int(config.get("chunk_size", 0x1000)),
    ) as uploader:
        uploader.upload_bin(bin_bytes, progress_cb=progress_cb, do_preflight=True)

    return "DM32UV picture upload complete. Power cycle the radio to see the new boot image."


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
    from ..protocol.logo_protocol import upload_logo as protocol_upload_logo

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
