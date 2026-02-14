"""
DM-32UV PowerOnPicture Protocol (reverse-engineered)

Implements the serial protocol used by the vendor "PowerOnPicture.exe" tool
to download (flash) a boot/power-on image to Baofeng DM-32 series radios.

Key facts (from static analysis of PowerOnPicture.exe):
- Serial: 115200 8N1, DTR/RTS asserted.
- Vendor .BIN format: 8-byte header + RGB565 payload (little-endian).
  On-wire transfer skips the first 8 bytes and streams RGB565 payload only.
- Main data packets are 'W' packets:
    0x57 | addr24_le | len16_le | payload[len]  then radio ACKs with 0x06

This module intentionally keeps unknowns configurable:
- base_addr: address base used to compute the 24-bit addr in 'W' packets.
  The EXE uses a local value as base; its exact origin wasn't conclusively
  recovered in this pass. Default is 0.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable, Optional, Tuple

try:
    import serial  # type: ignore
except ImportError:  # pragma: no cover
    serial = None

logger = logging.getLogger(__name__)


class DM32UVProtocolError(Exception):
    pass


@dataclass(frozen=True)
class DM32UVBinHeader:
    # Header as observed: word 0x1000 (bytes 00 10), width, height, byte6=0, byte7=0
    width: int
    height: int
    flags6: int = 0
    flags7: int = 0

    def to_bytes(self) -> bytes:
        if not (0 <= self.width <= 0xFFFF and 0 <= self.height <= 0xFFFF):
            raise DM32UVProtocolError("width/height must fit in uint16")
        if not (0 <= self.flags6 <= 0xFF and 0 <= self.flags7 <= 0xFF):
            raise DM32UVProtocolError("flags must fit in uint8")
        return (
            (0x1000).to_bytes(2, "little")
            + self.width.to_bytes(2, "little")
            + self.height.to_bytes(2, "little")
            + bytes([self.flags6 & 0xFF, self.flags7 & 0xFF])
        )


def rgb888_to_rgb565(r: int, g: int, b: int) -> int:
    r5 = (r >> 3) & 0x1F
    g6 = (g >> 2) & 0x3F
    b5 = (b >> 3) & 0x1F
    return (r5 << 11) | (g6 << 5) | b5


def build_dm32uv_bin_from_image(
    image_path: str,
    *,
    size: Tuple[int, int] = (240, 320),
) -> bytes:
    """
    Convert an image to the vendor DM32UV .BIN format:
      8-byte header + RGB565 little-endian payload.
    """
    from PIL import Image

    w, h = size
    img = Image.open(image_path)
    img = img.convert("RGB")
    img = img.resize((w, h), Image.Resampling.LANCZOS)

    header = DM32UVBinHeader(width=w, height=h).to_bytes()
    payload = bytearray()
    for y in range(h):
        for x in range(w):
            r, g, b = img.getpixel((x, y))
            v = rgb888_to_rgb565(r, g, b)
            payload.append(v & 0xFF)  # little-endian
            payload.append((v >> 8) & 0xFF)
    return header + bytes(payload)


def parse_dm32uv_bin(blob: bytes) -> Tuple[DM32UVBinHeader, bytes]:
    """
    Parse vendor .BIN and return (header, payload).
    Payload is RGB565 little-endian, starting after 8 bytes.
    """
    if len(blob) < 8:
        raise DM32UVProtocolError("BIN too short")
    magic = int.from_bytes(blob[0:2], "little")
    if magic != 0x1000:
        raise DM32UVProtocolError(f"Unexpected BIN magic 0x{magic:04X} (expected 0x1000)")
    w = int.from_bytes(blob[2:4], "little")
    h = int.from_bytes(blob[4:6], "little")
    hdr = DM32UVBinHeader(width=w, height=h, flags6=blob[6], flags7=blob[7])
    return hdr, blob[8:]


class DM32UVPictureUploader:
    """
    Serial uploader for the DM32UV picture protocol.
    """

    ACK = b"\x06"

    def __init__(
        self,
        port: str,
        *,
        baudrate: int = 115200,
        timeout: float = 0.5,
        write_timeout: float = 0.5,
        ack_timeout: float = 5.0,
        base_addr: int = 0,
        chunk_size: int = 0x1000,
    ) -> None:
        if serial is None:
            raise DM32UVProtocolError("PySerial not installed")
        if chunk_size <= 0 or chunk_size > 0xFFFF:
            raise DM32UVProtocolError("chunk_size must be 1..65535")
        if base_addr < 0 or base_addr > 0xFFFFFF:
            raise DM32UVProtocolError("base_addr must fit in 24 bits")

        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.write_timeout = write_timeout
        self.ack_timeout = ack_timeout
        self.base_addr = base_addr
        self.chunk_size = chunk_size
        self.ser: "serial.Serial | None" = None

    def open(self) -> None:
        self.ser = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            bytesize=8,
            parity="N",
            stopbits=1,
            timeout=self.timeout,
            write_timeout=self.write_timeout,
            rtscts=False,
            dsrdtr=False,
        )
        self.ser.dtr = True
        self.ser.rts = True
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()

    def close(self) -> None:
        if self.ser and self.ser.is_open:
            self.ser.close()

    def __enter__(self) -> "DM32UVPictureUploader":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _write(self, data: bytes) -> None:
        if not self.ser or not self.ser.is_open:
            raise DM32UVProtocolError("Serial port not open")
        n = self.ser.write(data)
        if n != len(data):
            raise DM32UVProtocolError(f"Incomplete write: {n}/{len(data)}")

    def _read_exact(self, n: int, *, timeout: Optional[float] = None) -> bytes:
        if not self.ser or not self.ser.is_open:
            raise DM32UVProtocolError("Serial port not open")
        if n <= 0:
            return b""
        if timeout is None:
            timeout = self.timeout
        deadline = time.time() + float(timeout)
        out = bytearray()
        while len(out) < n:
            if time.time() >= deadline:
                raise DM32UVProtocolError(f"Timeout reading {n} bytes (got {len(out)})")
            chunk = self.ser.read(n - len(out))
            if not chunk:
                continue
            out.extend(chunk)
        return bytes(out)

    def _read_ack(self, *, timeout: Optional[float] = None) -> None:
        b = self._read_exact(1, timeout=timeout)
        if b != self.ACK:
            raise DM32UVProtocolError(f"Expected ACK 0x06, got {b.hex()}")

    def preflight(self) -> None:
        """
        Best-effort reproduction of vendor preflight.

        Sequence (observed):
        - "PSEARCH" (ACK)
        - "PASSSTA" (ACK)
        - 56 00 00 40 0D (variable response)
        - 56 00 00 00 0E (variable response)
        - 47 00 00 00 00 01 (write)
        - read 0x106, must start with 'S'
        - FF FF FF FF 0C (write)
        - "PROGRAM" (ACK)
        - 0x02 (write) [ACK observed in the flow]
        """
        # PSEARCH (retry up to 5)
        for attempt in range(1, 6):
            self._write(b"PSEARCH")
            try:
                resp = self._read_exact(8, timeout=0.5)
                if resp[:1] == self.ACK:
                    break
            except DM32UVProtocolError:
                resp = b""
            if attempt >= 5:
                raise DM32UVProtocolError(f"PSEARCH failed (last resp={resp.hex() if resp else 'empty'})")

        # PASSSTA
        self._write(b"PASSSTA")
        resp = self._read_exact(8, timeout=0.5)
        if resp[:1] != self.ACK:
            raise DM32UVProtocolError(f"PASSSTA failed (resp={resp.hex()})")

        # V: 56 00 00 40 0D
        self._write(bytes([0x56, 0x00, 0x00, 0x40, 0x0D]))
        hdr = self._read_exact(3, timeout=0.5)
        if hdr[:1] != b"\x56":
            raise DM32UVProtocolError(f"V(0D) bad header: {hdr.hex()}")
        n = hdr[2]
        body = self._read_exact(n, timeout=0.5) if n else b""
        logger.debug("V(0D) resp hdr=%s body_len=%d", hdr.hex(), len(body))

        # V: 56 00 00 00 0E
        self._write(bytes([0x56, 0x00, 0x00, 0x00, 0x0E]))
        hdr = self._read_exact(3, timeout=0.5)
        if hdr[:1] != b"\x56":
            raise DM32UVProtocolError(f"V(0E) bad header: {hdr.hex()}")
        n = hdr[2]
        body = self._read_exact(n, timeout=0.5) if n else b""
        logger.debug("V(0E) resp hdr=%s body_len=%d", hdr.hex(), len(body))

        # G: 47 00 00 00 00 01
        self._write(bytes([0x47, 0x00, 0x00, 0x00, 0x00, 0x01]))

        # S-block: 0x106 bytes, starts with 'S'
        s = self._read_exact(0x106, timeout=0.5)
        if not s or s[:1] != b"S":
            raise DM32UVProtocolError(f"S-block invalid (first={s[:1].hex() if s else 'empty'})")
        logger.debug("S-block[0:32]=%s", s[:32].hex())

        # Marker
        self._write(bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x0C]))

        # PROGRAM
        self._write(b"PROGRAM")
        self._read_ack(timeout=0.5)

        # 0x02 (observed)
        self._write(b"\x02")
        # Some devices appear to ACK here; keep it tolerant.
        try:
            self._read_ack(timeout=0.5)
        except DM32UVProtocolError:
            pass

    def send_payload(
        self,
        payload: bytes,
        *,
        progress_cb: Optional[Callable[[int, int], None]] = None,
    ) -> None:
        """
        Send raw RGB565 payload bytes (no 8-byte header) via W packets.
        """
        total = len(payload)
        sent = 0
        for offset in range(0, total, self.chunk_size):
            chunk = payload[offset : offset + self.chunk_size]
            addr = (self.base_addr + offset) & 0xFFFFFF
            pkt = (
                b"\x57"
                + addr.to_bytes(3, "little")
                + len(chunk).to_bytes(2, "little")
                + chunk
            )
            self._write(pkt)
            self._read_ack(timeout=self.ack_timeout)
            sent += len(chunk)
            if progress_cb:
                progress_cb(sent, total)

    def upload_bin(
        self,
        bin_bytes: bytes,
        *,
        progress_cb: Optional[Callable[[int, int], None]] = None,
        do_preflight: bool = True,
    ) -> None:
        hdr, payload = parse_dm32uv_bin(bin_bytes)
        # Payload is RGB565.
        expected = hdr.width * hdr.height * 2
        if len(payload) != expected:
            raise DM32UVProtocolError(
                f"BIN payload length mismatch: got {len(payload)}, expected {expected} "
                f"({hdr.width}x{hdr.height}x2)"
            )

        if do_preflight:
            self.preflight()
        self.send_payload(payload, progress_cb=progress_cb)
