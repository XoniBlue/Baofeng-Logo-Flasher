"""
Boot logo read/write support for Baofeng radios.

UV-5RM/UV-5RH HARDWARE ARCHITECTURE (from reverse engineering):
================================================================
Based on: https://github.com/amoxu/Baofeng-UV-5RM-5RH-RE

Components:
- MCU: AT32F421C8T7 (64KB internal flash, 16KB SRAM)
- External Flash: XMC 25QH16CJIG - 16Mbit (2MB) SPI flash
- RF: BK4819

Memory Layout:
- MCU Internal Flash:
  - 0x08000000-0x08000FFF: Bootloader (4KB, protected)
  - 0x08001000-0x0800FFFF: Firmware (60KB)
- External SPI Flash (2MB):
  - Boot logo, audio prompts, and other assets

WHY DIRECT SERIAL FLASHING DOESN'T WORK:
=========================================
The clone protocol (CHIRP/UV17Pro) only accesses the MCU's internal memory.
Boot logos are stored on the EXTERNAL SPI flash chip, which requires:
1. Firmware-level access (the running firmware reads/writes SPI flash)
2. Or direct SPI programming via hardware

The clone protocol can only read/write channel data and settings from
the MCU memory range, NOT the external 2MB SPI flash where logos reside.

ALTERNATIVE APPROACHES:
=======================
1. Patch clone image file (if logo is cached in clone area - unlikely for UV-5RM)
2. Modify firmware and re-flash via bootloader (complex, risky)
3. Direct SPI flash programming via SWD/hardware (requires opening radio)

This module still attempts the clone protocol write for compatibility with
older radios that may store logos in MCU memory, but UV-5RM will reject writes.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Callable
import logging
import struct

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    serial = None

from PIL import Image

from .bmp_utils import (
    BmpInfo,
    validate_bmp_bytes,
    convert_image_to_bmp_bytes,
    parse_bmp_header,
)
from .protocol import UV5RMProtocol, RadioBlockError, RadioTransportError

# Import model registry for unified config
try:
    from .models import (
        get_model as registry_get_model,
        get_serial_flash_config as registry_get_flash_config,
        LogoRegion as RegistryLogoRegion,
    )
    _HAS_REGISTRY = True
except ImportError:
    _HAS_REGISTRY = False

logger = logging.getLogger(__name__)

BOOT_LOGO_SIZE = (160, 128)


@dataclass(frozen=True)
class LogoRegion:
    start: int
    length: int
    block_size: int


@dataclass(frozen=True)
class BootLogoModelConfig:
    name: str
    logo_region: Optional[LogoRegion]
    scan_ranges: List[Tuple[int, int]]


MODEL_CONFIGS: Dict[str, BootLogoModelConfig] = {
    "UV-5RH Pro": BootLogoModelConfig(
        name="UV-5RH Pro",
        logo_region=None,
        scan_ranges=[],
    ),
    "UV-17R": BootLogoModelConfig(
        name="UV-17R",
        logo_region=None,
        scan_ranges=[],
    ),
    "UV-17R Pro": BootLogoModelConfig(
        name="UV-17R Pro",
        logo_region=None,
        scan_ranges=[],
    ),
}

# Serial flashing protocol configs for direct boot logo flashing
# UV-5RM and UV-17Pro use the A5 framing logo protocol at 115200 baud.
#
# Protocol reference: LOGO_PROTOCOL.md from T6UV Series CPS Logo Tool capture.
#
# Supported radios:
# - UV-5RM: Uses A5 logo protocol, 160x128 RGB565
# - UV-17Pro: Uses A5 logo protocol, 160x128 RGB565
SERIAL_FLASH_CONFIGS: Dict[str, Dict] = {
    "UV-5RM": {
        "size": (160, 128),
        "color_mode": "RGB565",
        "protocol": "a5_logo",  # New A5 framing logo protocol
        "write_addr_mode": "chunk",  # CMD_WRITE addr increments by chunk index
        "baudrate": 115200,
        "timeout": 2.0,
        "chunk_size": 1024,
        "handshake": b"PROGRAMBFNORMALU",
        "handshake_ack": b"\x06",
    },
    "UV-17Pro": {
        "size": (160, 128),
        "color_mode": "RGB565",
        "protocol": "a5_logo",
        "write_addr_mode": "chunk",
        "baudrate": 115200,
        "timeout": 2.0,
        "chunk_size": 1024,
        "handshake": b"PROGRAMBFNORMALU",
        "handshake_ack": b"\x06",
    },
    "UV-17R": {
        "size": (160, 128),
        "color_mode": "RGB565",
        "protocol": "a5_logo",
        "write_addr_mode": "chunk",
        "baudrate": 115200,
        "timeout": 2.0,
        "chunk_size": 1024,
        "handshake": b"PROGRAMBFNORMALU",
        "handshake_ack": b"\x06",
    },
    # Legacy config for unsupported radios (not tested)
    "DM-32UV": {
        "size": (240, 320),
        "color_mode": "RGB",
        "protocol": "legacy",
        "encrypt": False,
        "start_addr": 0x2000,
        "magic": b"\x50\xBB\xFF\x20\x12\x07\x25",
        "block_size": 64,
        "baudrate": 9600,
        "timeout": 3.0,
    },
}


class BootLogoError(Exception):
    """Errors raised by boot logo operations."""


def baofeng_encrypt(data: bytes, key: bytes = b"\xAB\xCD\xEF") -> bytes:
    """Encrypt data using Baofeng algorithm (XOR + rotate)."""
    encrypted = bytearray()
    key_len = len(key)
    for i, byte in enumerate(data):
        enc_byte = byte ^ key[i % key_len]
        shift = i % 8
        enc_byte = ((enc_byte << shift) & 0xFF) | (enc_byte >> (8 - shift))
        encrypted.append(enc_byte)
    return bytes(encrypted)


def convert_bmp_to_raw(bmp_path: str, config: Dict) -> bytes:
    """Convert BMP file to raw format suitable for the target radio model."""
    size: Tuple[int, int] = config["size"]
    color_mode: str = config["color_mode"]
    encrypt: bool = config.get("encrypt", False)
    key: bytes = config.get("key", b"\xAB\xCD\xEF")

    img = Image.open(bmp_path)
    # Accept any image format, not just BMP
    img = img.convert("RGB")  # Ensure RGB mode first

    img = img.resize(size)
    img = img.transpose(Image.FLIP_TOP_BOTTOM)  # BMP bottom-up -> radio format

    if color_mode == "RGB332":
        raw = bytearray()
        for r, g, b in img.getdata():
            packed = ((r >> 5) << 5) | ((g >> 5) << 2) | (b >> 6)
            raw.append(struct.pack("B", packed)[0])
        raw_bytes = bytes(raw)
    elif color_mode == "RGB565":
        # Convert to RGB565 format (16-bit: RRRRRGGGGGGBBBBB)
        raw = bytearray()
        for r, g, b in img.getdata():
            r5 = (r >> 3) & 0x1F
            g6 = (g >> 2) & 0x3F
            b5 = (b >> 3) & 0x1F
            rgb565 = (r5 << 11) | (g6 << 5) | b5
            # Little-endian byte order
            raw.append(rgb565 & 0xFF)
            raw.append((rgb565 >> 8) & 0xFF)
        raw_bytes = bytes(raw)
    else:
        # Standard PIL color mode (RGB, L, etc.)
        img = img.convert(color_mode)
        raw_bytes = img.tobytes()

    if encrypt:
        raw_bytes = baofeng_encrypt(raw_bytes, key=key)

    return raw_bytes


def list_serial_ports() -> List[str]:
    """List available serial ports."""
    if not serial:
        return []
    return [p.device for p in serial.tools.list_ports.comports()]


def read_radio_id(
    port: str,
    magic: bytes = None,
    baudrate: int = 115200,  # Default to UV17Pro protocol
    timeout: float = 1.5,
    protocol: str = "uv17pro",  # "uv17pro" or "uv5r"
    post_ident_magics: list = None,
    fingerprint: bytes = b"\x06",
) -> str:
    """
    Connect to radio and read its ID using CHIRP-compatible handshake protocol.

    For UV-5RM, uses UV17Pro protocol from chirp/drivers/baofeng_uv17Pro.py.
    For legacy UV-5R variants, uses uv5r.py protocol.
    """
    if not serial:
        raise BootLogoError("PySerial not installed")

    import time

    if protocol == "uv17pro":
        # UV17Pro protocol (UV-5RM, UV-17, etc.)
        # Default magic for UV-5RM/UV17L
        if magic is None:
            magic = b"PROGRAMBFNORMALU"

        return _do_ident_uv17pro(port, magic, baudrate, timeout,
                                  post_ident_magics, fingerprint)
    else:
        # Legacy UV5R protocol (7-byte magic sequences)
        MAGIC_SEQUENCES = [
            b"\x50\xBB\xFF\x20\x12\x07\x25",  # UV5R BFB291+
            b"\x50\xBB\xFF\x01\x25\x98\x4D",  # UV5R Original
            b"\x50\xBB\xFF\x20\x13\x01\x05",  # UV82
            b"\x50\xBB\xFF\x20\x12\x08\x23",  # UV6
            b"\x50\xBB\xFF\x13\xA1\x11\xDD",  # F11
            b"\x50\xBB\xFF\x20\x14\x04\x13",  # A58
            b"\x50\xBB\xFF\x20\x12\x06\x25",  # UV5G
            b"\x50\xBB\xFF\x12\x03\x98\x4D",  # UV6 Original
        ]

        if magic is not None:
            sequences_to_try = [magic]
        else:
            sequences_to_try = MAGIC_SEQUENCES

        last_error = None

        for magic_seq in sequences_to_try:
            try:
                result = _do_ident_uv5r(port, magic_seq, 9600, timeout)
                return result
            except BootLogoError as e:
                last_error = e
                logger.debug(f"Magic {magic_seq.hex()} failed: {e}")
                time.sleep(0.5)

        if last_error:
            raise last_error
        raise BootLogoError("Radio did not respond to any known magic sequences")


def _do_ident_uv17pro(port: str, magic: bytes, baudrate: int, timeout: float,
                       post_ident_magics: list = None, fingerprint: bytes = b"\x06") -> str:
    """
    Perform identification handshake using UV17Pro protocol.
    Based on chirp/drivers/baofeng_uv17Pro.py _do_ident() function.
    """
    import time

    # UV17Pro uses NO hardware flow control, just like chirp/baofeng_common.py
    ser = serial.Serial(
        port=port,
        baudrate=baudrate,
        bytesize=8,
        parity='N',
        stopbits=1,
        timeout=timeout,
        write_timeout=timeout,
    )

    try:
        # Clean buffer first (CHIRP style)
        ser.timeout = 0.005
        junk = ser.read(256)
        if junk:
            logger.debug(f"Cleared {len(junk)} bytes of junk from buffer")
        ser.timeout = timeout

        logger.debug(f"Connected to {port} at {baudrate} baud (UV17Pro protocol)")
        logger.debug(f"Sending ident magic: {magic!r}")

        # Send the full magic string at once (UV17Pro style)
        ser.write(magic)

        # Read expected fingerprint response
        fingerprint_len = len(fingerprint)
        response = ser.read(fingerprint_len)

        if not response:
            raise BootLogoError(
                f"No response to ident magic. Is radio powered on and connected?"
            )

        if not response.startswith(fingerprint):
            logger.debug(f"Expected fingerprint {fingerprint.hex()}, got {response.hex()}")
            raise BootLogoError(
                f"Unexpected response: {response.hex()} (expected {fingerprint.hex()})"
            )

        logger.debug(f"Received fingerprint: {response.hex().upper()}")

        # Send additional magic commands (UV17Pro._magics)
        # The second response (0x4d) contains the model name
        model_name = None
        if post_ident_magics:
            for i, (cmd, resp_len) in enumerate(post_ident_magics):
                logger.debug(f"Sending post-ident magic: {cmd.hex()[:20]}...")
                ser.write(cmd)
                resp = ser.read(resp_len)
                logger.debug(f"Got response: {resp.hex() if resp else 'none'}")
                # Second magic response (0x4D) contains the model name in ASCII
                if i == 1 and resp:
                    try:
                        model_name = resp.decode('ascii', errors='ignore').strip()
                    except:
                        pass

        logger.debug("UV17Pro handshake complete")

        # Return model info if available, otherwise just fingerprint
        if model_name:
            return f"UV17Pro ({model_name})"
        return f"UV17Pro-{response.hex().upper()}"
    finally:
        ser.close()


def _do_ident_uv5r(port: str, magic: bytes, baudrate: int, timeout: float) -> str:
    """
    Perform identification handshake using legacy UV5R protocol.
    Based on chirp/drivers/uv5r.py _do_ident() function.
    """
    import time

    # Match CHIRP's serial config exactly - NO rtscts
    ser = serial.Serial(
        port=port,
        baudrate=baudrate,
        bytesize=8,
        parity='N',
        stopbits=1,
        timeout=timeout,
        write_timeout=timeout,
    )

    try:
        # Clean buffer first (CHIRP style)
        ser.timeout = 0.005
        junk = ser.read(256)
        if junk:
            logger.debug(f"Cleared {len(junk)} bytes of junk from buffer")
        ser.timeout = timeout

        logger.debug(f"Connected to {port} at {baudrate} baud (UV5R protocol)")
        logger.debug(f"Sending magic: {magic.hex().upper()}")

        # Send magic bytes one at a time with 10ms delay (CHIRP uv5r.py style)
        for byte in magic:
            ser.write(bytes([byte]))
            time.sleep(0.01)

        # Read ACK
        ack1 = ser.read(1)
        if ack1 != b'\x06':
            if ack1:
                logger.debug(f"Got: {ack1.hex()}")
            raise BootLogoError(
                f"No ACK after magic (got {ack1.hex() if ack1 else 'nothing'}). "
                f"Is radio powered on and connected?"
            )

        logger.debug("Received ACK")

        # Send 0x02 command
        ser.write(b'\x02')

        # Read identification (until 0xDD or max 12 bytes)
        ident_response = b""
        for i in range(12):
            byte = ser.read(1)
            if not byte:
                break
            ident_response += byte
            if byte == b'\xDD':
                break

        logger.debug(f"Received ident: {ident_response.hex().upper()}")

        # Validate response
        if len(ident_response) not in [8, 12]:
            raise BootLogoError(f"Invalid ident length: {len(ident_response)}")

        if not ident_response.startswith(b'\xAA') or not ident_response.endswith(b'\xDD'):
            raise BootLogoError(f"Invalid ident format: {ident_response.hex()}")

        # Send confirmation ACK
        ser.write(b'\x06')

        # Read second ACK
        ack2 = ser.read(1)
        if ack2 != b'\x06':
            raise BootLogoError(f"Radio refused clone (got {ack2.hex() if ack2 else 'nothing'})")

        logger.debug("Handshake complete")

        # Normalize 12-byte ident to 8 bytes (filter 0x01 bytes for UV-6)
        if len(ident_response) == 12:
            ident = bytes([b for b in ident_response if b != 0x01])[:8]
        else:
            ident = ident_response

        # Extract readable ID
        radio_id = ident[1:-1].decode(errors="ignore").strip("\x00")
        if not radio_id:
            radio_id = ident.hex().upper()

        return radio_id
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
    Flash boot logo to radio via serial connection.

    For UV-5RM, UV-17Pro, and UV-17R: Uses the A5 framing logo protocol.
    For legacy radios: Falls back to block write protocol.

    Args:
        port: Serial port path
        bmp_path: Path to image file (BMP, PNG, JPG, etc.)
        config: Model config from SERIAL_FLASH_CONFIGS
        simulate: If True, skip actual flash
        progress_cb: Optional callback(bytes_sent, total_bytes)
        debug_bytes: If True, dump payload/frame artifacts before send
        debug_output_dir: Optional output directory for debug artifacts
        write_address_mode: CMD_WRITE address semantics ("byte" or "chunk").
            If None, defaults from model config (write_addr_mode) or "byte".

    Returns:
        Success message string
    """
    if not serial and not simulate:
        raise BootLogoError("PySerial not installed")

    protocol_type = config.get("protocol", "legacy")
    effective_write_address_mode = write_address_mode or config.get("write_addr_mode", "byte")

    # Check for new A5 logo protocol (UV-5RM, UV-17Pro, etc.)
    if protocol_type == "a5_logo":
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
    else:
        return _flash_logo_legacy_protocol(port, bmp_path, config, simulate, progress_cb)


def _flash_logo_a5_protocol(
    port: str,
    bmp_path: str,
    config: Dict,
    simulate: bool = False,
    progress_cb: Optional[Callable[[int, int], None]] = None,
    debug_bytes: bool = False,
    debug_output_dir: Optional[str] = None,
    write_address_mode: str = "byte",
) -> str:
    """
    Flash logo using the A5 framing protocol for UV-5RM/UV-17Pro.

    This is the proper logo protocol captured from the T6UV CPS Logo Tool.
    Protocol sequence:
    1. PROGRAMBFNORMALU handshake → 0x06 ACK
    2. 'D' to enter logo mode
    3. Init frame (cmd 0x02)
    4. Config frame (cmd 0x04) at 0x4504
    5. Setup frame (cmd 0x03)
    6. Image data in 1024-byte chunks (cmd 0x57)
    7. Completion frame (cmd 0x06) with "Over"
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

    logger.info(f"Flashing logo using A5 protocol to {port}")
    return protocol_upload_logo(
        port,
        bmp_path,
        progress_cb,
        simulate=False,
        debug_bytes=debug_bytes,
        debug_output_dir=debug_output_dir,
        address_mode=write_address_mode,
    )


def _flash_logo_legacy_protocol(
    port: str,
    bmp_path: str,
    config: Dict,
    simulate: bool = False,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> str:
    """
    Flash logo using legacy block write protocol (for older radios).

    This protocol uses 'X' command with address and data blocks.
    Not recommended for UV-5RM/UV-17Pro - use A5 protocol instead.
    """
    raw_data = convert_bmp_to_raw(bmp_path, config)
    block_size = int(config.get("block_size", 64))
    start_addr = int(config.get("start_addr", 0x1000))
    magic = config.get("magic", b"PROGRAMBFNORMALU")
    baudrate = int(config.get("baudrate", 115200))
    timeout = float(config.get("timeout", 3.0))

    if simulate:
        return f"Simulation: {len(raw_data)} bytes to 0x{start_addr:04X} via {port}"

    ser = serial.Serial(port, baudrate, timeout=timeout)
    try:
        import time

        # Clear buffers and initialize
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        time.sleep(0.1)

        radio_id = "UNKNOWN"

        # Legacy UV5R Protocol with 7-byte magic
        logger.debug(f"Flashing to {port}: Using legacy block write protocol")

        # Send magic bytes one at a time with 10ms delay
        for byte in magic:
            ser.write(bytes([byte]))
            ser.flush()
            time.sleep(0.01)

        # Receive ACK
        ack = ser.read(1)
        if ack != b"\x06":
            raise BootLogoError(
                f"No ACK from radio (got {ack.hex() if ack else 'nothing'}). Is it powered on?"
            )

        # Send mode request
        ser.write(b"\x02")
        ser.flush()

        # Receive identification
        ident_response = b""
        for i in range(12):
            byte = ser.read(1)
            if not byte:
                break
            ident_response += byte
            if byte == b'\xDD':
                break

        if ident_response:
            radio_id = ident_response[1:-1].decode(errors="ignore").strip("\x00")
            if not radio_id:
                radio_id = ident_response.hex().upper()

        # Send confirmation
        ser.write(b"\x06")
        ser.flush()

        # Receive second ACK
        ack2 = ser.read(1)

        logger.debug(f"Handshake complete. Radio ID: {radio_id}")

        # Write logo blocks
        addr = start_addr
        total = len(raw_data)
        written = 0

        for i in range(0, total, block_size):
            block = raw_data[i : i + block_size]
            block_len = len(block)

            # Write protocol: 'X' (0x58) + addr (2 bytes BE) + length (1 byte) + data
            cmd = struct.pack(">BHB", ord('X'), addr, block_len) + block
            ser.write(cmd)
            ser.flush()
            time.sleep(0.05)

            ack = ser.read(1)
            if not ack or ack != b"\x06":
                ack_val = ack.hex() if ack else 'nothing'
                if ack == b'R':
                    hint = "Radio returned 'R' (0x52) - address is read-only."
                elif ack == b'E':
                    hint = "Radio returned 'E' (0x45) - command error."
                elif ack == b'\x15':
                    hint = "Radio returned NAK (0x15)."
                else:
                    hint = f"Unexpected response: 0x{ack_val}"

                raise BootLogoError(
                    f"Write failed at 0x{addr:04X} (got {ack_val}). {hint}"
                )

            addr += block_len
            written += block_len

            if progress_cb:
                progress_cb(written, total)

        ser.write(b"E")
        ser.flush()
        return f"Logo flashed! Radio: {radio_id}. Power cycle the radio."
    finally:
        ser.close()


def baofeng_decrypt(data: bytes, key: bytes = b"\xAB\xCD\xEF") -> bytes:
    """Decrypt data using Baofeng algorithm (reverse of encrypt: rotate back + XOR)."""
    decrypted = bytearray()
    key_len = len(key)
    for i, byte in enumerate(data):
        shift = i % 8
        # Reverse the rotation first
        dec_byte = ((byte >> shift) | ((byte << (8 - shift)) & 0xFF)) & 0xFF
        # Then XOR with key
        dec_byte = dec_byte ^ key[i % key_len]
        decrypted.append(dec_byte)
    return bytes(decrypted)


def convert_raw_to_bmp(raw_data: bytes, config: Dict) -> bytes:
    """Convert raw radio format to BMP file bytes."""
    size: Tuple[int, int] = config["size"]
    color_mode: str = config.get("color_mode", "RGB")
    encrypt: bool = config.get("encrypt", False)
    key: bytes = config.get("key", b"\xAB\xCD\xEF")

    # Decrypt if needed
    if encrypt:
        raw_data = baofeng_decrypt(raw_data, key=key)

    # Create image from raw data
    if color_mode == "RGB332":
        # Expand RGB332 to RGB
        pixels = []
        for byte in raw_data:
            r = ((byte >> 5) & 0x07) * 36  # 3 bits to 8 bits
            g = ((byte >> 2) & 0x07) * 36  # 3 bits to 8 bits
            b = (byte & 0x03) * 85          # 2 bits to 8 bits
            pixels.append((r, g, b))
        img = Image.new("RGB", size)
        img.putdata(pixels)
    else:
        # Assume RGB (3 bytes per pixel)
        expected_size = size[0] * size[1] * 3
        if len(raw_data) < expected_size:
            # Pad with zeros if needed
            raw_data = raw_data + b'\x00' * (expected_size - len(raw_data))
        img = Image.frombytes(color_mode, size, raw_data[:expected_size])

    # Flip back (radio format is bottom-up like BMP)
    img = img.transpose(Image.FLIP_TOP_BOTTOM)

    # Convert to BMP bytes
    import io
    buffer = io.BytesIO()
    img.save(buffer, format="BMP")
    return buffer.getvalue()


def read_logo(
    port: str,
    config: Dict,
    simulate: bool = False,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> Tuple[bytes, str]:
    """
    Read boot logo from radio via serial connection.

    Uses the same handshake protocol as flash_logo to ensure compatibility.

    Returns:
        Tuple of (raw_bytes, radio_id)
    """
    if not serial and not simulate:
        raise BootLogoError("PySerial not installed")

    size = config["size"]
    # Calculate expected logo size (RGB = 3 bytes per pixel)
    color_mode = config.get("color_mode", "RGB")
    if color_mode == "RGB332":
        total_bytes = size[0] * size[1]  # 1 byte per pixel
    else:
        total_bytes = size[0] * size[1] * 3  # 3 bytes per pixel

    block_size = int(config.get("block_size", 64))
    start_addr = int(config["start_addr"])
    magic = config["magic"]
    baudrate = int(config.get("baudrate", 115200))
    timeout = float(config.get("timeout", 3.0))

    if simulate:
        # Return dummy data for simulation
        dummy_data = bytes([0x00] * total_bytes)
        return dummy_data, "SIMULATED"

    ser = serial.Serial(port, baudrate, timeout=timeout)
    try:
        import time

        # Clear buffers and initialize
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        time.sleep(0.1)

        # Use EXACTLY the same handshake as flash_logo (which works)
        # Send magic bytes one at a time with 10ms delay
        logger.debug(f"Reading from {port}: Sending magic bytes")
        for byte in magic:
            ser.write(bytes([byte]))
            ser.flush()
            time.sleep(0.01)

        ack = ser.read(1)
        if ack != b"\x06":
            raise BootLogoError(
                f"No response from radio (got {ack.hex() if ack else 'nothing'}). Is it powered on at {port}?"
            )

        # Send mode request and receive identification
        ser.write(b"\x02")
        ser.flush()

        ident_response = b""
        for i in range(12):
            byte = ser.read(1)
            if not byte:
                break
            ident_response += byte
            if byte == b'\xDD':
                break

        radio_id = ident_response[1:-1].decode(errors="ignore").strip("\x00") if ident_response else "UNKNOWN"
        if not radio_id:
            radio_id = ident_response.hex().upper() if ident_response else "UNKNOWN"

        # Send confirmation and receive second ACK
        ser.write(b"\x06")
        ser.flush()
        ack2 = ser.read(1)

        logger.debug(f"Handshake complete. Radio ID: {radio_id}")

        # === Read logo blocks ===
        # Use 'S' command for read: S + addr(2) + size(1)
        # Response: X + addr(2) + size(1) + data
        data = bytearray()
        addr = start_addr
        read_bytes = 0

        for i in range(0, total_bytes, block_size):
            remaining = min(block_size, total_bytes - i)

            # Send read command: 'S' + addr (2 bytes BE) + size (1 byte)
            cmd = struct.pack(">BHB", ord('S'), addr, remaining)
            ser.write(cmd)
            ser.flush()
            time.sleep(0.05)

            # Read response header: 'X' + addr (2 bytes) + size (1 byte)
            hdr = ser.read(4)
            if len(hdr) != 4:
                # If we got partial data, read more with longer timeout
                if len(hdr) > 0:
                    ser.timeout = timeout * 2
                    more = ser.read(4 - len(hdr))
                    hdr += more
                    ser.timeout = timeout

                if len(hdr) != 4:
                    raise BootLogoError(
                        f"Incomplete response at 0x{addr:04X} (got {len(hdr)} bytes: {hdr.hex() if hdr else 'none'}). "
                        f"Radio may not support logo read at this address."
                    )

            resp_cmd, resp_addr, resp_size = struct.unpack(">BHB", hdr)

            if resp_cmd != ord('X'):
                raise BootLogoError(
                    f"Invalid response command at 0x{addr:04X}: got 0x{resp_cmd:02X}, expected 0x{ord('X'):02X}. "
                    f"Full header: {hdr.hex()}"
                )

            # Read data block
            block = ser.read(resp_size)
            if len(block) != resp_size:
                raise BootLogoError(
                    f"Incomplete block at 0x{addr:04X}: expected {resp_size}, got {len(block)}"
                )

            data.extend(block)

            # Send ACK
            ser.write(b"\x06")
            ser.flush()
            time.sleep(0.02)

            addr += remaining
            read_bytes += remaining

            if progress_cb:
                progress_cb(read_bytes, total_bytes)

        # End session
        ser.write(b"E")
        ser.flush()

        return bytes(data), radio_id
    finally:
        ser.close()


class BootLogoService:
    def __init__(self, protocol: UV5RMProtocol):
        self.protocol = protocol

    def resolve_model_config(self, model_name: str) -> BootLogoModelConfig:
        """Resolve model configuration, checking registry first."""
        # Check legacy MODEL_CONFIGS first for backward compatibility
        if model_name in MODEL_CONFIGS:
            return MODEL_CONFIGS[model_name]

        # Try registry if available
        if _HAS_REGISTRY:
            reg_config = registry_get_model(model_name)
            if reg_config:
                # Convert registry config to BootLogoModelConfig
                logo_region = None
                if reg_config.logo_regions:
                    r = reg_config.logo_regions[0]
                    logo_region = LogoRegion(
                        start=r.start_addr,
                        length=r.length,
                        block_size=r.block_size,
                    )
                return BootLogoModelConfig(
                    name=reg_config.name,
                    logo_region=logo_region,
                    scan_ranges=[],
                )

        raise BootLogoError(f"Unsupported model: {model_name}")

    def resolve_logo_region(
        self,
        model_config: BootLogoModelConfig,
        logo_start: Optional[int] = None,
        logo_length: Optional[int] = None,
        block_size: Optional[int] = None,
    ) -> LogoRegion:
        if logo_start is not None and logo_length is not None:
            region_block = block_size or 0x40
            return LogoRegion(start=logo_start, length=logo_length, block_size=region_block)

        if model_config.logo_region is None:
            raise BootLogoError(
                "Logo region not configured for this model. "
                "Provide --logo-start/--logo-length or run discovery."
            )

        if block_size is not None:
            return LogoRegion(
                start=model_config.logo_region.start,
                length=model_config.logo_region.length,
                block_size=block_size,
            )

        return model_config.logo_region

    def read_logo(self, region: LogoRegion) -> bytes:
        self._validate_region(region)
        data = bytearray()
        end = region.start + region.length

        for addr in range(region.start, end, region.block_size):
            size = min(region.block_size, end - addr)
            block = self.protocol.read_block(addr, size)
            data.extend(block)

        return bytes(data)

    def write_logo(self, region: LogoRegion, data: bytes) -> None:
        self._validate_region(region)

        if len(data) != region.length:
            raise BootLogoError(
                f"Logo data length {len(data)} does not match region length {region.length}"
            )

        end = region.start + region.length
        offset = 0

        for addr in range(region.start, end, region.block_size):
            size = min(region.block_size, end - addr)
            chunk = data[offset:offset + size]
            self.protocol.write_block(addr, chunk)
            offset += size

    def validate_logo_bytes(self, data: bytes) -> BmpInfo:
        return validate_bmp_bytes(data, BOOT_LOGO_SIZE)

    def prepare_logo_bytes(self, image_path: str) -> bytes:
        try:
            with open(image_path, "rb") as handle:
                raw = handle.read()
            self.validate_logo_bytes(raw)
            return raw
        except Exception:
            return convert_image_to_bmp_bytes(image_path, BOOT_LOGO_SIZE)

    def discover_logo_region(
        self,
        scan_ranges: List[Tuple[int, int]],
        block_size: int = 0x40,
        scan_stride: int = 0x10,
    ) -> LogoRegion:
        if not scan_ranges:
            raise BootLogoError("No scan ranges provided for discovery")

        header_size = 54

        for start, end in scan_ranges:
            if end <= start:
                continue
            for addr in range(start, end - header_size, scan_stride):
                try:
                    header = self.protocol.read_block(addr, min(block_size, header_size))
                    if len(header) < 2 or header[0:2] != b"BM":
                        continue

                    if len(header) < header_size:
                        header += self.protocol.read_block(
                            addr + len(header), header_size - len(header)
                        )

                    info = parse_bmp_header(header, allow_partial=True)
                    if (info.width, info.height) != BOOT_LOGO_SIZE:
                        continue
                    length = info.file_size
                    if length <= 0:
                        continue
                    expected_file_size = info.data_offset + info.image_size
                    if length != expected_file_size:
                        continue

                    if addr + length <= end:
                        logger.info(
                            "Discovered BMP at 0x%04X length %d", addr, length
                        )
                        return LogoRegion(start=addr, length=length, block_size=block_size)
                except (RadioBlockError, RadioTransportError, ValueError):
                    continue

        raise BootLogoError("No valid BMP logo found in scan ranges")

    def _validate_region(self, region: LogoRegion) -> None:
        if region.start < 0 or region.length <= 0:
            raise BootLogoError("Invalid logo region")
        if region.block_size <= 0:
            raise BootLogoError("Invalid block size")
        if region.start > 0xFFFF or (region.start + region.length) > 0x10000:
            raise BootLogoError("Logo region out of 16-bit address range")
