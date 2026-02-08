"""
UV-17Pro / UV-5RM Logo Protocol Implementation

Based on the T6UV Series CPS Logo Tool protocol capture.
Reference: LOGO_PROTOCOL.md

This module implements the boot logo upload protocol for Baofeng UV-17Pro
and UV-5RM radios using the A5 framing protocol at 115200 baud.

Protocol sequence:
1. Send PROGRAMBFNORMALU (16 bytes) → expect 0x06
2. Send 'D' (0x44) to enter logo mode (no response expected)
3. Send init frame (cmd 0x02) with "PROGRAM" → expect ACK with 'Y'
4. Send config frame (cmd 0x04) at 0x4504 → expect ACK
5. Send setup frame (cmd 0x03) → expect ACK
6. Send image in 1004-byte chunks (cmd 0x57) → expect data ACK (0xEE)
7. Send completion frame (cmd 0x06) with "Over" → expect 0x00
"""

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Optional, Callable, Tuple, List, Literal

try:
    import serial
except ImportError:
    serial = None

logger = logging.getLogger(__name__)

# Protocol constants
BAUD_RATE = 115200
HANDSHAKE_MAGIC = b"PROGRAMBFNORMALU"
HANDSHAKE_ACK = b"\x06"
LOGO_MODE_CMD = b"D"

# A5 Frame commands
CMD_INIT = 0x02
CMD_SETUP = 0x03
CMD_CONFIG = 0x04
CMD_COMPLETE = 0x06
CMD_WRITE = 0x57  # 'W'
CMD_DATA_ACK = 0xEE

# Addresses
ADDR_CONFIG = 0x4504
ADDR_IMAGE_BASE = 0x0000

# Image specs
IMAGE_WIDTH = 160
IMAGE_HEIGHT = 128
IMAGE_BYTES = IMAGE_WIDTH * IMAGE_HEIGHT * 2  # RGB565 = 2 bytes per pixel
CHUNK_SIZE = 1024  # Bytes per frame for image data (len=0x0400 in captures)
CONFIG_PAYLOAD = bytes([0x00, 0x00, 0x0C, 0x00, 0x00, 0x01])
SETUP_PAYLOAD = bytes([0x00, 0x00, 0x0C, 0x00])


class LogoProtocolError(Exception):
    """Errors raised by logo protocol operations."""


def crc16_xmodem(data: bytes) -> int:
    """
    Calculate CRC16-XMODEM checksum.

    This is the checksum algorithm used by the UV-17Pro/UV-5RM logo protocol.
    The checksum is calculated on all frame bytes AFTER the 0xA5 start byte.
    Result is stored in big-endian format (high byte first).

    Args:
        data: Bytes to calculate checksum over (excluding 0xA5 prefix)

    Returns:
        16-bit CRC value
    """
    crc = 0
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return crc


def build_frame(cmd: int, addr: int, payload: bytes) -> bytes:
    """
    Build an A5 frame.

    Frame format:
    [ 0xA5 | cmd | addr_hi | addr_lo | len_hi | len_lo | payload | checksum (2) ]

    The checksum is CRC16-XMODEM calculated over all bytes after 0xA5,
    stored in big-endian format.

    Args:
        cmd: Command byte (0x02, 0x03, 0x04, 0x06, 0x57)
        addr: 16-bit address
        payload: Payload bytes

    Returns:
        Complete frame as bytes
    """
    frame = bytearray([0xA5, cmd])
    frame.append((addr >> 8) & 0xFF)  # addr high
    frame.append(addr & 0xFF)          # addr low
    frame.append((len(payload) >> 8) & 0xFF)  # len high
    frame.append(len(payload) & 0xFF)         # len low
    frame.extend(payload)

    # Calculate CRC16-XMODEM over all bytes after 0xA5
    crc = crc16_xmodem(bytes(frame[1:]))  # Skip 0xA5

    # Append CRC in big-endian order
    frame.append((crc >> 8) & 0xFF)   # CRC high byte
    frame.append(crc & 0xFF)           # CRC low byte

    return bytes(frame)


def chunk_image_data(
    image_data: bytes,
    chunk_size: int = CHUNK_SIZE,
    pad_last_chunk: bool = False,
) -> List[Tuple[int, bytes]]:
    """
    Split image bytes into (offset, chunk) tuples used for CMD_WRITE frames.

    Args:
        image_data: Raw image payload bytes
        chunk_size: Bytes per chunk/frame payload
        pad_last_chunk: If True, right-pad final chunk with zeroes

    Returns:
        List[(offset, payload_chunk)] where offset is byte offset from image base
    """
    chunks: List[Tuple[int, bytes]] = []
    for offset in range(0, len(image_data), chunk_size):
        chunk = image_data[offset:offset + chunk_size]
        if pad_last_chunk and len(chunk) < chunk_size:
            chunk = chunk + bytes(chunk_size - len(chunk))
        chunks.append((offset, chunk))
    return chunks


def _calc_write_addr(offset: int, chunk_size: int, mode: str) -> int:
    """Calculate CMD_WRITE address field from byte offset."""
    if mode == "byte":
        return offset
    if mode == "chunk":
        return offset // chunk_size
    raise ValueError(f"Unknown write address mode: {mode}")


def build_write_frames(
    image_data: bytes,
    chunk_size: int = CHUNK_SIZE,
    pad_last_chunk: bool = False,
    address_mode: Literal["byte", "chunk"] = "byte",
) -> List[Tuple[int, bytes, bytes]]:
    """
    Build CMD_WRITE frames for image payload.

    Returns:
        List[(offset, chunk_payload, frame_bytes)]
    """
    frames: List[Tuple[int, bytes, bytes]] = []
    for offset, chunk in chunk_image_data(image_data, chunk_size, pad_last_chunk):
        addr = _calc_write_addr(offset, chunk_size, address_mode)
        frames.append((addr, chunk, build_frame(CMD_WRITE, addr, chunk)))
    return frames


def parse_response(data: bytes) -> Tuple[int, int, int, bytes]:
    """
    Parse an A5 response frame.

    Returns:
        Tuple of (cmd, addr, length, payload)
    """
    if len(data) < 6 or data[0] != 0xA5:
        raise LogoProtocolError(f"Invalid response frame: {data.hex() if data else 'empty'}")

    cmd = data[1]
    addr = (data[2] << 8) | data[3]
    length = (data[4] << 8) | data[5]
    payload = data[6:6+length] if length > 0 else b""

    return cmd, addr, length, payload


def rgb888_to_bgr565(r: int, g: int, b: int) -> int:
    """
    Convert RGB888 to BGR565 format (what the radio expects).

    BGR565 bit layout: BBBBBGGGGGGRRRRR
    """
    r5 = (r >> 3) & 0x1F
    g6 = (g >> 2) & 0x3F
    b5 = (b >> 3) & 0x1F
    return (b5 << 11) | (g6 << 5) | r5


def convert_image_to_rgb565(image_path: str, size: Tuple[int, int] = (160, 128)) -> bytes:
    """
    Convert an image file to BGR565 format suitable for the radio.

    Args:
        image_path: Path to image file (PNG, JPG, BMP, etc.)
        size: Target dimensions (width, height)

    Returns:
        Raw BGR565 bytes in little-endian format
    """
    from PIL import Image

    img = Image.open(image_path)
    img = img.convert("RGB")
    img = img.resize(size, Image.Resampling.LANCZOS)

    # No vertical flip - radio reads top-to-bottom
    # Convert to BGR565 little-endian
    raw_data = bytearray()
    for y in range(size[1]):
        for x in range(size[0]):
            r, g, b = img.getpixel((x, y))
            bgr565 = rgb888_to_bgr565(r, g, b)
            # Little-endian: low byte first
            raw_data.append(bgr565 & 0xFF)
            raw_data.append((bgr565 >> 8) & 0xFF)

    return bytes(raw_data)


def render_rgb565_payload_row_major(
    image_data: bytes,
    width: int = IMAGE_WIDTH,
    height: int = IMAGE_HEIGHT,
) -> "Image.Image":
    """
    Render row-major little-endian BGR565 payload back to an RGB PIL image.
    """
    from PIL import Image

    expected = width * height * 2
    payload = image_data[:expected]
    if len(payload) < expected:
        payload = payload + b"\x00" * (expected - len(payload))

    img = Image.new("RGB", (width, height))
    pixels = img.load()

    i = 0
    for y in range(height):
        for x in range(width):
            val = payload[i] | (payload[i + 1] << 8)
            i += 2

            # BGR565: BBBBB GGGGGG RRRRR
            b5 = (val >> 11) & 0x1F
            g6 = (val >> 5) & 0x3F
            r5 = val & 0x1F

            r = (r5 << 3) | (r5 >> 2)
            g = (g6 << 2) | (g6 >> 4)
            b = (b5 << 3) | (b5 >> 2)
            pixels[x, y] = (r, g, b)

    return img


def dump_logo_debug_artifacts(
    image_data: bytes,
    write_frames: List[Tuple[int, bytes, bytes]],
    output_dir: str,
    max_hex_bytes: int = 256,
    address_mode: str = "byte",
) -> Path:
    """
    Dump deterministic byte artifacts for protocol comparisons/debugging.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    payload_path = out_dir / "image_payload.bin"
    payload_path.write_bytes(image_data)

    frame_payload_stream = b"".join(chunk for _, chunk, _ in write_frames)
    frame_payload_path = out_dir / "write_payload_stream.bin"
    frame_payload_path.write_bytes(frame_payload_stream)

    frames_path = out_dir / "write_frames.bin"
    frames_path.write_bytes(b"".join(frame for _, _, frame in write_frames))

    preview_path = out_dir / "preview_row_major.png"
    render_rgb565_payload_row_major(image_data, IMAGE_WIDTH, IMAGE_HEIGHT).save(preview_path)

    manifest = {
        "image_bytes": len(image_data),
        "chunk_size": CHUNK_SIZE,
        "address_mode": address_mode,
        "frame_count": len(write_frames),
        "first_offsets": [offset for offset, _, _ in write_frames[:8]],
        "payload_sha256": hashlib.sha256(image_data).hexdigest(),
        "frame_payload_sha256": hashlib.sha256(frame_payload_stream).hexdigest(),
        "first_bytes_hex": image_data[:max_hex_bytes].hex(),
    }
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest_path


class LogoUploader:
    """
    Handles boot logo upload to UV-17Pro / UV-5RM radios.
    """

    def __init__(
        self,
        port: str,
        baudrate: int = BAUD_RATE,
        timeout: float = 2.0,
    ):
        """
        Initialize uploader.

        Args:
            port: Serial port path
            baudrate: Baud rate (default 115200)
            timeout: Read timeout in seconds
        """
        if serial is None:
            raise LogoProtocolError("PySerial not installed")

        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser: "serial.Serial | None" = None

    def open(self) -> None:
        """Open serial connection."""
        self.ser = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            bytesize=8,
            parity='N',
            stopbits=1,
            timeout=self.timeout,
            write_timeout=self.timeout,
        )
        # Hold DTR/RTS high as per protocol
        self.ser.dtr = True
        self.ser.rts = True

        # Clear any stale data
        time.sleep(0.1)
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()

        # Read and discard any garbage in the buffer
        self.ser.timeout = 0.05
        garbage = self.ser.read(1024)
        if garbage:
            logger.debug(f"Cleared {len(garbage)} bytes of stale data: {garbage.hex()}")
        self.ser.timeout = self.timeout

        logger.debug(f"Opened {self.port} at {self.baudrate} baud")

    def close(self) -> None:
        """Close serial connection."""
        if self.ser and self.ser.is_open:
            self.ser.close()
            logger.debug(f"Closed {self.port}")

    def _send(self, data: bytes) -> None:
        """Send data to radio."""
        if not self.ser or not self.ser.is_open:
            raise LogoProtocolError("Serial port not open")
        self.ser.write(data)
        self.ser.flush()
        logger.debug(f">>> {data[:32].hex()}" + ("..." if len(data) > 32 else ""))

    def _recv(self, length: int) -> bytes:
        """Receive data from radio."""
        if not self.ser or not self.ser.is_open:
            raise LogoProtocolError("Serial port not open")
        data = self.ser.read(length)
        if data:
            logger.debug(f"<<< {data.hex()}")
        return data

    def handshake(self) -> None:
        """
        Perform initial handshake.

        Send: PROGRAMBFNORMALU (16 bytes)
        Recv: 0x06 (ACK)
        """
        logger.info("Performing handshake...")
        self._send(HANDSHAKE_MAGIC)
        time.sleep(0.1)

        response = self._recv(1)
        if response != HANDSHAKE_ACK:
            raise LogoProtocolError(
                f"Handshake failed: expected 0x06, got {response.hex() if response else 'nothing'}. "
                "Is the radio powered on and connected?"
            )
        logger.debug("Handshake successful")

    def enter_logo_mode(self) -> None:
        """
        Enter logo mode.

        Send: 'D' (0x44)
        No response expected.
        """
        logger.info("Entering logo mode...")
        self._send(LOGO_MODE_CMD)
        # Give radio time to switch to logo mode
        time.sleep(0.2)

    def send_init_frame(self) -> None:
        """
        Send initialization frame.

        Send: A5 02 00 00 00 07 "PROGRAM" + checksum
        Recv: A5 02 00 00 00 01 59 (ACK with 'Y')
        """
        logger.info("Sending init frame...")
        frame = build_frame(CMD_INIT, 0x0000, b"PROGRAM")
        logger.debug(f"Init frame bytes: {frame.hex()}")
        self._send(frame)
        time.sleep(0.1)

        response = self._recv(9)
        logger.debug(f"Init frame response: {response.hex() if response else 'empty'}")
        if len(response) < 7:
            raise LogoProtocolError(f"Init frame: incomplete response ({len(response)} bytes)")

        cmd, addr, length, payload = parse_response(response)
        if cmd != CMD_INIT or (payload and payload[0:1] != b'Y'):
            raise LogoProtocolError(f"Init frame: unexpected response {response.hex()}")

        logger.debug("Init frame acknowledged")

    def send_config_frame(self) -> None:
        """
        Send config frame at address 0x4504.

        Send: A5 04 45 04 00 06 [config payload] + checksum
        Recv: A5 04 45 04 00 01 59 (ACK)
        """
        logger.info("Sending config frame...")
        frame = build_frame(CMD_CONFIG, ADDR_CONFIG, CONFIG_PAYLOAD)
        self._send(frame)
        time.sleep(0.02)

        response = self._recv(9)
        if len(response) < 7:
            raise LogoProtocolError(f"Config frame: incomplete response ({len(response)} bytes)")

        cmd, addr, length, payload = parse_response(response)
        if cmd != CMD_CONFIG or (payload and payload[0:1] != b'Y'):
            raise LogoProtocolError(f"Config frame: unexpected response {response.hex()}")

        logger.debug("Config frame acknowledged")

    def send_setup_frame(self) -> None:
        """
        Send setup frame.

        Send: A5 03 00 00 00 04 [setup payload] + checksum
        Recv: A5 03 00 00 00 01 59 (ACK)
        """
        logger.info("Sending setup frame...")
        frame = build_frame(CMD_SETUP, 0x0000, SETUP_PAYLOAD)
        self._send(frame)
        time.sleep(0.02)

        response = self._recv(9)
        if len(response) < 7:
            raise LogoProtocolError(f"Setup frame: incomplete response ({len(response)} bytes)")

        cmd, addr, length, payload = parse_response(response)
        if cmd != CMD_SETUP or (payload and payload[0:1] != b'Y'):
            raise LogoProtocolError(f"Setup frame: unexpected response {response.hex()}")

        logger.debug("Setup frame acknowledged")

    def send_image_data(
        self,
        image_data: bytes,
        progress_cb: Optional[Callable[[int, int], None]] = None,
        address_mode: Literal["byte", "chunk"] = "byte",
    ) -> None:
        """
        Send image data in chunks.

        Each chunk:
        Send: A5 57 [addr_hi] [addr_lo] 04 00 [1004 bytes] + checksum
        Recv: A5 EE 00 00 00 01 04 + checksum (data ACK)

        Args:
            image_data: Raw RGB565 image data
            progress_cb: Optional callback(bytes_sent, total_bytes)
        """
        total = len(image_data)
        sent = 0

        logger.info(f"Sending {total} bytes of image data in {CHUNK_SIZE}-byte chunks...")

        if total % CHUNK_SIZE != 0:
            logger.warning(
                "Image payload size %d is not aligned to %d-byte chunks; final frame will be short",
                total,
                CHUNK_SIZE,
            )

        for offset, chunk in chunk_image_data(
            image_data,
            chunk_size=CHUNK_SIZE,
            pad_last_chunk=False,
        ):
            write_addr = _calc_write_addr(offset, CHUNK_SIZE, address_mode)

            # Build frame with address offset
            frame = build_frame(CMD_WRITE, write_addr, chunk)
            self._send(frame)
            time.sleep(0.01)

            # Wait for data ACK
            # Expected: A5 EE ... (data ACK) OR A5 57 ... 59 (write echo with 'Y')
            response = self._recv(9)
            if len(response) < 7:
                raise LogoProtocolError(
                    f"Image data at offset 0x{offset:04X} (addr=0x{write_addr:04X}): incomplete ACK ({len(response)} bytes)"
                )

            cmd, addr, length, payload = parse_response(response)

            # Accept either:
            # - CMD_DATA_ACK (0xEE) with any payload
            # - CMD_WRITE (0x57) with 'Y' payload (echo-style ACK)
            if cmd == CMD_DATA_ACK:
                pass  # Expected ACK format
            elif cmd == CMD_WRITE and payload and payload[0:1] == b'Y':
                pass  # Echo-style ACK with 'Y'
            else:
                raise LogoProtocolError(
                    f"Image data at offset 0x{offset:04X} (addr=0x{write_addr:04X}): unexpected response {response.hex()}"
                )

            sent += len(chunk)
            if progress_cb:
                progress_cb(sent, total)

            logger.debug(
                "Chunk offset=0x%04X addr=0x%04X acknowledged (%d/%d bytes)",
                offset,
                write_addr,
                sent,
                total,
            )

    def send_completion_frame(self) -> None:
        """
        Send completion frame.

        Send: A5 06 00 00 00 04 "Over" + checksum
        Recv: 0x00
        """
        logger.info("Sending completion frame...")
        frame = build_frame(CMD_COMPLETE, 0x0000, b"Over")
        self._send(frame)
        time.sleep(0.02)

        response = self._recv(1)
        if response and response != b'\x00':
            logger.warning(f"Completion: unexpected response {response.hex()}, continuing anyway")
        else:
            logger.debug("Completion acknowledged")

    def upload_logo(
        self,
        image_path: str,
        progress_cb: Optional[Callable[[int, int], None]] = None,
        debug_bytes: bool = False,
        debug_output_dir: Optional[str] = None,
        address_mode: Literal["byte", "chunk"] = "byte",
    ) -> str:
        """
        Complete logo upload workflow.

        Args:
            image_path: Path to image file (any format PIL can read)
            progress_cb: Optional progress callback(bytes_sent, total_bytes)

        Returns:
            Success message string
        """
        try:
            self.open()

            # Convert image to RGB565
            logger.info(f"Converting image to RGB565 ({IMAGE_WIDTH}x{IMAGE_HEIGHT})...")
            image_data = convert_image_to_rgb565(image_path, (IMAGE_WIDTH, IMAGE_HEIGHT))

            if len(image_data) != IMAGE_BYTES:
                raise LogoProtocolError(
                    f"Image data size mismatch: expected {IMAGE_BYTES}, got {len(image_data)}"
                )

            if debug_bytes:
                frames = build_write_frames(
                    image_data,
                    chunk_size=CHUNK_SIZE,
                    pad_last_chunk=False,
                    address_mode=address_mode,
                )
                out_dir = debug_output_dir or "out/logo_debug"
                manifest_path = dump_logo_debug_artifacts(
                    image_data,
                    frames,
                    out_dir,
                    address_mode=address_mode,
                )
                logger.info("Wrote debug byte artifacts to %s", manifest_path.parent)

            # Execute protocol sequence
            self.handshake()
            self.enter_logo_mode()
            self.send_init_frame()
            self.send_config_frame()
            self.send_setup_frame()
            self.send_image_data(image_data, progress_cb, address_mode=address_mode)
            self.send_completion_frame()

            return "Logo upload complete! Power cycle the radio to see the new boot logo."

        finally:
            self.close()


def upload_logo(
    port: str,
    image_path: str,
    progress_cb: Optional[Callable[[int, int], None]] = None,
    simulate: bool = False,
    debug_bytes: bool = False,
    debug_output_dir: Optional[str] = None,
    address_mode: Literal["byte", "chunk"] = "byte",
) -> str:
    """
    Convenience function to upload a boot logo.

    Args:
        port: Serial port path
        image_path: Path to image file
        progress_cb: Optional progress callback
        simulate: If True, skip actual upload

    Returns:
        Success/status message
    """
    if simulate:
        # Just validate the image
        from PIL import Image
        img = Image.open(image_path)
        return (
            f"Simulation: Would upload {img.size[0]}x{img.size[1]} image "
            f"to {port} as {IMAGE_WIDTH}x{IMAGE_HEIGHT} RGB565"
        )

    uploader = LogoUploader(port)
    return uploader.upload_logo(
        image_path,
        progress_cb,
        debug_bytes=debug_bytes,
        debug_output_dir=debug_output_dir,
        address_mode=address_mode,
    )
