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

import logging
import time
from typing import Optional, Callable, Tuple

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
CHUNK_SIZE = 1004  # Bytes per frame for image data


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
        # Config payload: Try 0x29 (41 chunks) instead of 0x0C (12 = compressed?)
        config_payload = bytes([0x00, 0x00, 0x29, 0x00, 0x00, 0x01])
        frame = build_frame(CMD_CONFIG, ADDR_CONFIG, config_payload)
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
        # Setup payload: Match config - 0x29 for raw mode
        setup_payload = bytes([0x00, 0x00, 0x29, 0x00])
        frame = build_frame(CMD_SETUP, 0x0000, setup_payload)
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

        for offset in range(0, total, CHUNK_SIZE):
            chunk = image_data[offset:offset + CHUNK_SIZE]

            # Pad last chunk if needed
            if len(chunk) < CHUNK_SIZE:
                chunk = chunk + bytes(CHUNK_SIZE - len(chunk))

            # Build frame with address offset
            frame = build_frame(CMD_WRITE, offset, chunk)
            self._send(frame)
            time.sleep(0.01)

            # Wait for data ACK
            # Expected: A5 EE ... (data ACK) OR A5 57 ... 59 (write echo with 'Y')
            response = self._recv(9)
            if len(response) < 7:
                raise LogoProtocolError(
                    f"Image data at offset 0x{offset:04X}: incomplete ACK ({len(response)} bytes)"
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
                    f"Image data at offset 0x{offset:04X}: unexpected response {response.hex()}"
                )

            sent += len(chunk)
            if progress_cb:
                progress_cb(sent, total)

            logger.debug(f"Chunk at 0x{offset:04X} acknowledged ({sent}/{total} bytes)")

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

            # Execute protocol sequence
            self.handshake()
            self.enter_logo_mode()
            self.send_init_frame()
            self.send_config_frame()
            self.send_setup_frame()
            self.send_image_data(image_data, progress_cb)
            self.send_completion_frame()

            return "Logo upload complete! Power cycle the radio to see the new boot logo."

        finally:
            self.close()


def upload_logo(
    port: str,
    image_path: str,
    progress_cb: Optional[Callable[[int, int], None]] = None,
    simulate: bool = False,
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
    return uploader.upload_logo(image_path, progress_cb)
