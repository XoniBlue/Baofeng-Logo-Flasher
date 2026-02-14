"""
Firmware tools for UV-5RM/5RH style .BF packages and serial workflows.

This module ports the key C utilities from amoxu/Baofeng-UV-5RM-5RH-RE:
- reverse_engineering/encrypt.c
- reverse_engineering/decrypt.c
- reverse_engineering/uv5rm-wrap-tool/*

It also provides host-side Python helpers for:
- "make extract"/"make rebuild" equivalents
- Serial firmware flashing over K-plug (bootloader protocol style)
- Dumper serial monitoring and dump-log parsing
- Optional "dumper-flash" helper through pyOCD, with graceful fallback
"""

from __future__ import annotations

import os
import re
import struct
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    import serial  # type: ignore
except Exception:
    serial = None


PACKAGE_SIZE = 1024
XOR_KEY1 = b"KDHT"
XOR_KEY2 = b"RBGI"
FW_FLASH_BASE = 0x08001000
FW_FLASH_LIMIT = 60 * 1024
SYSBTLDR_ADDR = 0x1FFFE400
SYSBTLDR_SIZE = 0x1000
BOOTLOADER_SIZE = 0x1000


class FirmwareToolError(Exception):
    """Base exception for firmware tool operations."""


class FirmwareProtocolError(FirmwareToolError):
    """Raised when serial protocol exchange fails."""


@dataclass(frozen=True)
class BFHeader:
    """Header layout for wrapped .BF images."""

    region_count: int
    firmware_len: int
    data_len: int
    reserved: bytes


@dataclass
class DumpSegment:
    """Single parsed segment from dumper UART output."""

    name: str
    start_address: int
    data: bytes


@dataclass
class DumperCapture:
    """Raw + parsed dumper monitor output."""

    raw_lines: List[str]
    segments: Dict[str, DumpSegment]


@dataclass
class MakeActionResult:
    """Result for make-like helper commands."""

    ok: bool
    message: str
    artifacts: Dict[str, str]
    command: Optional[List[str]] = None


def xor_crypt_block(data: bytes, key: bytes) -> bytes:
    """Port of xor_encrypt/xor_decrypt byte rules from upstream C."""
    out = bytearray(len(data))
    for i, byte in enumerate(data):
        key_byte = key[i % 4]
        if byte not in (0x00, 0xFF, key_byte, key_byte ^ 0xFF):
            out[i] = byte ^ key_byte
        else:
            out[i] = byte
    return bytes(out)


def crypt_firmware_payload(data: bytes, key1: bytes = XOR_KEY1, key2: bytes = XOR_KEY2) -> bytes:
    """
    Port of encrypt.c/decrypt.c package loop.

    Rules:
    - Package size: 1024 bytes
    - First 2 packages: plaintext
    - Last 2 packages: plaintext
    - Middle packages:
      - i % 3 == 1 -> XOR key1
      - i % 3 == 2 -> XOR key2
      - i % 3 == 0 -> plaintext
    """
    if not data:
        return data

    package_count, rem = divmod(len(data), PACKAGE_SIZE)
    if rem:
        package_count += 1

    out = bytearray()
    for i in range(package_count):
        start = i * PACKAGE_SIZE
        end = min(start + PACKAGE_SIZE, len(data))
        block = data[start:end]
        if i >= 2 and i < package_count - 2:
            if i % 3 == 1:
                block = xor_crypt_block(block, key1)
            elif i % 3 == 2:
                block = xor_crypt_block(block, key2)
        out.extend(block)
    return bytes(out[: len(data)])


def parse_bf_header(blob: bytes) -> BFHeader:
    """Parse the 16-byte BF wrapper header."""
    if len(blob) < 16:
        raise FirmwareToolError("BF file too small: missing 16-byte header")
    region_count = blob[0]
    firmware_len = int.from_bytes(blob[1:5], "big")
    data_len = int.from_bytes(blob[5:9], "big")
    reserved = bytes(blob[9:16])
    return BFHeader(region_count=region_count, firmware_len=firmware_len, data_len=data_len, reserved=reserved)


def unwrap_bf_bytes(
    bf_blob: bytes,
    *,
    decrypt_firmware: bool = True,
    decrypt_data: bool = False,
) -> Tuple[bytes, bytes, BFHeader]:
    """
    Unwrap BF into firmware + data regions.

    `decrypt_data=False` matches upstream uv5rm-wrap-tool behavior.
    """
    header_raw = parse_bf_header(bf_blob)
    if header_raw.region_count not in (1, 2):
        raise FirmwareToolError(f"Unsupported BF region_count={header_raw.region_count}")

    # Some real-world BF files set cntPart=1 but leave the "data_len" field
    # uninitialized/garbage. Upstream tooling and the bootloader ignore it
    # when region_count == 1, so normalize it to 0 to avoid confusion.
    header = header_raw
    if header.region_count == 1 and header.data_len != 0:
        header = BFHeader(
            region_count=header_raw.region_count,
            firmware_len=header_raw.firmware_len,
            data_len=0,
            reserved=header_raw.reserved,
        )

    fw_start = 16
    fw_end = fw_start + header.firmware_len
    if fw_end > len(bf_blob):
        raise FirmwareToolError("BF file truncated while reading firmware region")
    firmware = bytes(bf_blob[fw_start:fw_end])

    data = b""
    if header.region_count == 2 and header.data_len > 0:
        data_end = fw_end + header.data_len
        if data_end > len(bf_blob):
            raise FirmwareToolError("BF file truncated while reading data region")
        data = bytes(bf_blob[fw_end:data_end])

    if decrypt_firmware:
        firmware = crypt_firmware_payload(firmware)
    if decrypt_data and data:
        data = crypt_firmware_payload(data)

    return firmware, data, header


def wrap_bf_bytes(
    firmware: bytes,
    data: bytes = b"",
    *,
    encrypt_firmware: bool = True,
    encrypt_data: bool = False,
    reserved: Optional[bytes] = None,
) -> bytes:
    """Wrap firmware/data to BF format, mirroring uv5rm-wrap-tool defaults."""
    fw_blob = crypt_firmware_payload(firmware) if encrypt_firmware else firmware
    data_blob = data
    if encrypt_data and data_blob:
        data_blob = crypt_firmware_payload(data_blob)

    region_count = 2 if data_blob else 1
    if reserved is None:
        reserved = b"\x00" * 7
    if len(reserved) != 7:
        raise FirmwareToolError("reserved field must be exactly 7 bytes")

    header = bytearray(16)
    header[0] = region_count
    header[1:5] = len(fw_blob).to_bytes(4, "big")
    header[5:9] = len(data_blob).to_bytes(4, "big")
    header[9:16] = reserved
    return bytes(header) + fw_blob + data_blob


def make_extract_equivalent(
    input_bf: str | Path,
    output_fw_bin: str | Path,
    output_data_bin: Optional[str | Path] = None,
    *,
    decrypt_firmware: bool = True,
    decrypt_data: bool = False,
) -> MakeActionResult:
    """Equivalent to 'make extract' for BF -> BIN."""
    in_path = Path(input_bf)
    out_fw = Path(output_fw_bin)
    fw, data, header = unwrap_bf_bytes(
        in_path.read_bytes(),
        decrypt_firmware=decrypt_firmware,
        decrypt_data=decrypt_data,
    )
    out_fw.write_bytes(fw)
    artifacts: Dict[str, str] = {"firmware_bin": str(out_fw)}
    if data:
        out_data = Path(output_data_bin) if output_data_bin else out_fw.with_suffix(out_fw.suffix + ".data")
        out_data.write_bytes(data)
        artifacts["data_bin"] = str(out_data)
    return MakeActionResult(
        ok=True,
        message=(
            f"Extracted BF (regions={header.region_count}, firmware={header.firmware_len}B, "
            f"data={header.data_len}B)"
        ),
        artifacts=artifacts,
    )


def make_rebuild_equivalent(
    input_fw_bin: str | Path,
    output_bf: str | Path,
    input_data_bin: Optional[str | Path] = None,
    *,
    encrypt_firmware: bool = True,
    encrypt_data: bool = False,
) -> MakeActionResult:
    """Equivalent to 'make rebuild' for BIN -> BF."""
    fw = Path(input_fw_bin).read_bytes()
    data = Path(input_data_bin).read_bytes() if input_data_bin else b""
    wrapped = wrap_bf_bytes(
        fw,
        data=data,
        encrypt_firmware=encrypt_firmware,
        encrypt_data=encrypt_data,
    )
    out = Path(output_bf)
    out.write_bytes(wrapped)
    artifacts = {"bf_file": str(out)}
    if data:
        artifacts["data_bin"] = str(input_data_bin)
    return MakeActionResult(ok=True, message=f"Rebuilt BF ({len(wrapped)} bytes)", artifacts=artifacts)


def make_all_equivalent() -> MakeActionResult:
    """Equivalent to a lightweight 'make all' setup check in pure Python."""
    missing = []
    if serial is None:
        missing.append("pyserial")
    try:
        import streamlit as _st  # noqa: F401
    except Exception:
        missing.append("streamlit")
    msg = "Environment ready" if not missing else f"Missing optional dependencies: {', '.join(missing)}"
    return MakeActionResult(ok=not missing, message=msg, artifacts={})


def make_dumper_flash_equivalent(
    firmware_path: str | Path,
    *,
    target: str = "at32f421x8",
    probe: Optional[str] = None,
    dry_run: bool = False,
) -> MakeActionResult:
    """
    Equivalent to 'make dumper-flash' using pyOCD when available.

    If pyOCD is unavailable, returns manual instructions.
    """
    fw_path = Path(firmware_path)
    if not fw_path.exists():
        return MakeActionResult(ok=False, message=f"Firmware path not found: {fw_path}", artifacts={})

    cmd = ["pyocd", "flash", "-t", target]
    if probe:
        cmd += ["-u", probe]
    cmd.append(str(fw_path))
    if dry_run:
        return MakeActionResult(ok=True, message="Dry-run only", artifacts={}, command=cmd)

    try:
        proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    except FileNotFoundError:
        return MakeActionResult(
            ok=False,
            message=(
                "pyOCD not found. Install with 'pip install pyocd' or flash dumper manually via SWD "
                "(OpenOCD/ST-Link/J-Link), then use dumper monitor over K-plug."
            ),
            artifacts={},
            command=cmd,
        )

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        return MakeActionResult(ok=False, message=f"pyOCD flash failed: {err}", artifacts={}, command=cmd)

    return MakeActionResult(ok=True, message="Dumper firmware flashed via pyOCD", artifacts={}, command=cmd)


def parse_hex_byte_string(value: str) -> bytes:
    """Parse bytes from strings like '01 02 ff' or '0x01,0x02,0xFF'."""
    cleaned = value.replace(",", " ").replace("0x", "").replace("0X", "").strip()
    if not cleaned:
        return b""
    parts = [p for p in cleaned.split() if p]
    out = bytearray()
    for p in parts:
        if len(p) > 2:
            raise FirmwareToolError(f"Invalid byte token: {p}")
        out.append(int(p, 16))
    return bytes(out)


def patch_firmware_at_offset(blob: bytes, offset: int, patch_bytes: bytes) -> bytes:
    """Apply an in-memory patch at absolute firmware offset."""
    if offset < 0:
        raise FirmwareToolError("Offset must be >= 0")
    end = offset + len(patch_bytes)
    if end > len(blob):
        raise FirmwareToolError(f"Patch out of range (end=0x{end:X}, size=0x{len(blob):X})")
    out = bytearray(blob)
    out[offset:end] = patch_bytes
    return bytes(out)


def apply_unlock_frequency_patch(blob: bytes, *, value: int = 0x01, offset: int = 0xF255) -> bytes:
    """Apply one-byte patch often used during experiments."""
    if not (0 <= value <= 0xFF):
        raise FirmwareToolError("Patch byte value must fit in uint8")
    return patch_firmware_at_offset(blob, offset, bytes([value]))


def list_factory_firmware(factory_root: str | Path) -> List[Path]:
    """List BF files under a factory_firmware directory."""
    root = Path(factory_root)
    if not root.exists():
        return []
    return sorted(root.rglob("*.BF"))


_SECTION_RE = re.compile(r"^\*{3}\s*(.+?)\s*\*{3}\s*$")
_HEX_RE = re.compile(r"^0x([0-9A-Fa-f]{8})((?:\s+[0-9A-Fa-f]{2})+)\s*$")


def parse_dumper_log_lines(lines: Iterable[str]) -> Dict[str, DumpSegment]:
    """Parse output like reverse_engineering/dump.log into binary segments."""
    segments: Dict[str, Tuple[int, bytearray]] = {}
    current_name: Optional[str] = None

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        section_match = _SECTION_RE.match(line)
        if section_match:
            current_name = section_match.group(1).strip().upper().replace(" ", "_")
            if current_name not in segments:
                segments[current_name] = (-1, bytearray())
            continue

        match = _HEX_RE.match(line)
        if not match:
            continue
        if not current_name:
            current_name = "UNLABELED"
            if current_name not in segments:
                segments[current_name] = (-1, bytearray())

        addr = int(match.group(1), 16)
        row_bytes = bytes(int(part, 16) for part in match.group(2).split())
        start_addr, buf = segments[current_name]

        if start_addr < 0:
            start_addr = addr
            segments[current_name] = (start_addr, buf)

        expected = start_addr + len(buf)
        if addr > expected:
            buf.extend(b"\xFF" * (addr - expected))
        elif addr < expected:
            continue
        buf.extend(row_bytes)

    out: Dict[str, DumpSegment] = {}
    for name, (start, data) in segments.items():
        if start >= 0 and data:
            out[name] = DumpSegment(name=name, start_address=start, data=bytes(data))
    return out


def monitor_dumper_serial_guided(
    port: str,
    *,
    baudrate: int = 115200,
    timeout: float = 0.35,
    max_seconds: float = 45.0,
    idle_seconds: float = 3.0,
    log_cb: Optional[Callable[[str], None]] = None,
    interactive: bool = True,
) -> DumperCapture:
    """
    Monitor the dumper's UART output with power-cycle guidance.

    Important: the dumper firmware is a one-shot tool. It prints once on boot
    and then typically enters an infinite loop. To capture output reliably:
    - open the serial port first
    - then power on / power-cycle the radio
    """
    if serial is None:
        raise FirmwareToolError("PySerial is required for serial monitoring")

    if interactive:
        print("=" * 70)
        print("DUMPER MONITOR SETUP")
        print("=" * 70)
        print("The dumper firmware runs once on power-up and outputs to UART.")
        print("Ensure the radio is powered OFF before starting.")
        print("")
        input("Press ENTER when the radio is OFF and ready...")

    ser = serial.Serial(
        port=port,
        baudrate=baudrate,
        bytesize=8,
        parity="N",
        stopbits=1,
        timeout=timeout,
        write_timeout=timeout,
    )

    if interactive:
        print("=" * 70)
        print("Serial monitor is ACTIVE and waiting for data")
        print("=" * 70)
        print("Power ON the radio NOW to capture dumper output.")
        print(f"Monitoring at {baudrate} baud for up to {max_seconds} seconds...")
        print(f"(Auto-stops after {idle_seconds} seconds of idle once data starts.)")

    lines: List[str] = []
    start = time.time()
    last_rx = start
    bytes_received = 0
    try:
        while True:
            now = time.time()
            if now - start >= max_seconds:
                if log_cb:
                    log_cb(f"[Monitor] Stopped: max time ({max_seconds}s) reached")
                break
            if now - last_rx >= idle_seconds and lines:
                if log_cb:
                    log_cb(f"[Monitor] Stopped: idle timeout ({idle_seconds}s)")
                break

            chunk = ser.readline()
            if not chunk:
                continue
            last_rx = time.time()
            bytes_received += len(chunk)
            line = chunk.decode("utf-8", errors="ignore").rstrip("\r\n")
            lines.append(line)
            if log_cb:
                log_cb(line)

            if interactive and len(lines) == 1:
                print(f"Data detected at {baudrate} baud; capturing...")
    finally:
        ser.close()

    segments = parse_dumper_log_lines(lines)
    if interactive:
        print("=" * 70)
        print("CAPTURE COMPLETE")
        print("=" * 70)
        print(f"Lines received: {len(lines)}")
        print(f"Bytes received: {bytes_received}")
        if not segments:
            print("WARNING: No dump segments detected.")
            print("If you saw no output at all, try:")
            print("- different baud rates (9600/19200/38400/57600/115200)")
            print("- verifying TX/RX wiring and that your K-plug matches the UART used by the dumper")
            print("- power-cycling again (the dumper is one-shot)")

    return DumperCapture(raw_lines=lines, segments=segments)


def scan_dumper_baud_rates(
    port: str,
    *,
    baud_rates: List[int] = [9600, 19200, 38400, 57600, 115200],
    test_duration: float = 5.0,
) -> Dict[int, int]:
    """
    Scan multiple baud rates to see which one receives dumper output.

    Note: you must power-cycle the radio for each baud rate attempt (one-shot dumper).
    Returns a dict of {baud_rate: bytes_received}.
    """
    if serial is None:
        raise FirmwareToolError("PySerial is required for serial monitoring")

    results: Dict[int, int] = {}
    print("=" * 70)
    print("BAUD RATE SCANNER")
    print("=" * 70)
    print("Power-cycle the radio for EACH test (dumper output is one-shot).")

    for i, baud in enumerate(baud_rates, start=1):
        print(f"\n[Test {i}/{len(baud_rates)}] {baud} baud")
        input("Ensure radio is POWERED OFF, then press ENTER...")

        ser = serial.Serial(
            port=port,
            baudrate=baud,
            bytesize=8,
            parity="N",
            stopbits=1,
            timeout=0.1,
            write_timeout=0.1,
        )
        print("Monitor active. Power ON the radio NOW.")

        start = time.time()
        total_bytes = 0
        try:
            while time.time() - start < test_duration:
                chunk = ser.readline()
                if not chunk:
                    continue
                total_bytes += len(chunk)
        finally:
            ser.close()

        results[baud] = total_bytes
        if total_bytes > 0:
            print(f"  DATA DETECTED: {total_bytes} bytes")
        else:
            print("  No data detected")

    print("\n" + "=" * 70)
    print("SCAN RESULTS")
    print("=" * 70)
    for baud, bytes_rx in sorted(results.items(), key=lambda kv: kv[1], reverse=True):
        marker = "OK " if bytes_rx > 0 else "   "
        print(f"{marker}{baud:6d} baud: {bytes_rx:6d} bytes")

    if results and max(results.values()) > 0:
        best = max(results.items(), key=lambda kv: kv[1])[0]
        print(f"\nRecommended: {best} baud")
    else:
        print("\nNo data detected at any baud rate.")
        print("Troubleshooting:")
        print("- verify USB-serial adapter and port selection")
        print("- verify TX/RX wiring (swap if unsure)")
        print("- the dumper may be using a different UART than the K-plug wiring")

    return results


def monitor_serial_raw(
    port: str,
    *,
    baudrate: int = 115200,
    duration: float = 10.0,
    hex_display: bool = False,
) -> bytes:
    """
    Raw serial monitor with no line parsing.

    Useful when readline-based monitoring shows nothing (wrong line endings,
    binary noise, etc.).
    """
    if serial is None:
        raise FirmwareToolError("PySerial is required for serial monitoring")

    print("=" * 70)
    print("RAW SERIAL MONITOR")
    print("=" * 70)
    print(f"Port: {port}")
    print(f"Baud: {baudrate}")
    print(f"Duration: {duration}s")
    input("Ensure radio is OFF, then press ENTER...")

    ser = serial.Serial(
        port=port,
        baudrate=baudrate,
        bytesize=8,
        parity="N",
        stopbits=1,
        timeout=0.1,
        write_timeout=0.1,
    )
    print("Monitor active. Power ON the radio NOW.")

    start = time.time()
    all_data = bytearray()
    try:
        while time.time() - start < duration:
            chunk = ser.read(64)
            if not chunk:
                continue
            all_data.extend(chunk)
            if hex_display:
                print(" ".join(f"{b:02X}" for b in chunk))
            else:
                # ASCII-ish display; show non-printables as <XX>
                out = []
                for b in chunk:
                    if 32 <= b < 127:
                        out.append(chr(b))
                    else:
                        out.append(f"<{b:02X}>")
                print("".join(out))
    finally:
        ser.close()

    print("=" * 70)
    print(f"Captured {len(all_data)} bytes total")
    return bytes(all_data)


def monitor_dumper_serial(
    port: str,
    *,
    baudrate: int = 115200,
    timeout: float = 0.35,
    max_seconds: float = 45.0,
    idle_seconds: float = 3.0,
    log_cb: Optional[Callable[[str], None]] = None,
) -> DumperCapture:
    """
    LEGACY: Monitor dumper output without guided power-cycle prompts.

    Warning: if the radio is already powered on, the dumper has likely already
    run and you may capture nothing. Prefer monitor_dumper_serial_guided().
    """
    return monitor_dumper_serial_guided(
        port=port,
        baudrate=baudrate,
        timeout=timeout,
        max_seconds=max_seconds,
        idle_seconds=idle_seconds,
        log_cb=log_cb,
        interactive=False,
    )


def save_capture_segments(capture: DumperCapture, output_dir: str | Path) -> Dict[str, Path]:
    """Write parsed dumper segments to files."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    saved: Dict[str, Path] = {}
    for name, seg in capture.segments.items():
        safe = name.lower()
        path = out_dir / f"{safe}.bin"
        path.write_bytes(seg.data)
        saved[name] = path
    raw_path = out_dir / "dumper_raw.log"
    raw_path.write_text("\n".join(capture.raw_lines) + ("\n" if capture.raw_lines else ""), encoding="utf-8")
    saved["RAW_LOG"] = raw_path
    return saved


def crc16_ccitt(dat: bytes, offset: int = 0, count: Optional[int] = None, *, poly: int = 0x1021, init: int = 0) -> int:
    """
    CRC16-CCITT implementation compatible with vendor flasher (poly 0x1021, init 0).

    Matches `PackageFmt` findings:
    - CRC computed over `[cmd, cmdArgs, dataLen_hi, dataLen_lo, data...]`.
    """
    if offset < 0:
        raise FirmwareToolError("offset must be >= 0")
    if count is None:
        count = len(dat) - offset
    if count < 0:
        raise FirmwareToolError("count must be >= 0")
    end = offset + count
    if end > len(dat):
        raise FirmwareToolError("crc range out of bounds")

    crc = init & 0xFFFF
    for b in dat[offset:end]:
        crc ^= (b & 0xFF) << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ poly) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc & 0xFFFF


@dataclass(frozen=True)
class VendorPacket:
    """Single vendor-protocol packet (0xAA ... CRC16 ... 0xEF)."""

    cmd: int
    cmd_args: int
    data: bytes


def pack_vendor_packet(cmd: int, cmd_args: int, data: bytes = b"") -> bytes:
    """
    Pack a vendor-protocol packet.

    Layout:
      0xAA | cmd | cmdArgs | dataLen_be_u16 | data | crc16_be_u16 | 0xEF
    """
    if not (0 <= cmd <= 0xFF):
        raise FirmwareToolError("cmd must fit in uint8")
    if not (0 <= cmd_args <= 0xFF):
        raise FirmwareToolError("cmd_args must fit in uint8")
    if data is None:
        data = b""
    if len(data) > 0xFFFF:
        raise FirmwareToolError("data too large for uint16 length")

    data_len = len(data)
    hdr = bytes([0xAA, cmd & 0xFF, cmd_args & 0xFF]) + data_len.to_bytes(2, "big")
    body = hdr + data
    crc = crc16_ccitt(body, offset=1, count=4 + data_len)
    return body + crc.to_bytes(2, "big") + b"\xEF"


def unpack_vendor_packet(blob: bytes) -> VendorPacket:
    """Parse a single complete vendor packet and validate framing + CRC."""
    if len(blob) < 1 + 1 + 1 + 2 + 2 + 1:
        raise FirmwareProtocolError("packet too short")
    if blob[0] != 0xAA:
        raise FirmwareProtocolError("missing 0xAA start byte")
    if blob[-1] != 0xEF:
        raise FirmwareProtocolError("missing 0xEF end byte")
    cmd = blob[1]
    cmd_args = blob[2]
    data_len = int.from_bytes(blob[3:5], "big")
    expected_len = 1 + 1 + 1 + 2 + data_len + 2 + 1
    if len(blob) != expected_len:
        raise FirmwareProtocolError(f"packet length mismatch: got {len(blob)}, expected {expected_len}")
    data = blob[5 : 5 + data_len]
    want_crc = int.from_bytes(blob[5 + data_len : 5 + data_len + 2], "big")
    got_crc = crc16_ccitt(blob, offset=1, count=4 + data_len)
    if got_crc != want_crc:
        raise FirmwareProtocolError(f"CRC16 mismatch: got 0x{got_crc:04X}, want 0x{want_crc:04X}")
    return VendorPacket(cmd=cmd, cmd_args=cmd_args, data=data)


class VendorFirmwareFlasher:
    """
    Vendor upgrade protocol implementation (from decompiled Windows flasher).

    Reference: ilspy/PROTOCOL_FINDINGS.md

    High-level flow:
      Raw serial handshake: PROGRAM + model_tag + 0x55, ACK; UPDATE, ACK
      Then framed packets (0xAA ... CRC16 ... 0xEF):
        66 -> 1("BOOTLOADER") -> 4(count1) -> 3(chunks) -> 5(count2) -> 3(chunks) -> 69
    """

    CMD_HANDSHAKE = 1
    CMD_UPDATE = 3
    CMD_UPDATE_DATA_PACKAGES = 4
    CMD_UPDATE_DATA_PACKAGES2 = 5
    CMD_UPDATE_END = 69
    CMD_INTO_BOOT = 66

    # Observed error codes (packet.Command) when CommandArgs != 6
    ERR_HANDSHAKE_CODE = 225
    ERR_DATA_CHECK = 226
    ERR_ADDRESS = 227
    ERR_FLASH_WRITE = 228
    ERR_COMMAND = 229

    def __init__(
        self,
        port: str,
        *,
        baudrate: int = 115200,
        timeout: float = 1.0,
        retries: int = 5,
        model_tag: bytes = b"BFNORMAL",
    ) -> None:
        if serial is None:
            raise FirmwareToolError("PySerial is required for flashing")
        if retries < 1:
            raise FirmwareToolError("retries must be >= 1")
        if not model_tag:
            raise FirmwareToolError("model_tag must not be empty")

        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.retries = retries
        self.model_tag = model_tag
        self.ser = None

    def open(self) -> None:
        self.ser = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            bytesize=8,
            parity="N",
            stopbits=1,
            timeout=self.timeout,
            write_timeout=self.timeout,
            rtscts=False,
            dsrdtr=False,
        )
        # Vendor tool sets both enables.
        self.ser.dtr = True
        self.ser.rts = True
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()

    def close(self) -> None:
        if self.ser and self.ser.is_open:
            self.ser.close()

    def __enter__(self) -> "VendorFirmwareFlasher":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _write(self, data: bytes) -> None:
        if not self.ser or not self.ser.is_open:
            raise FirmwareProtocolError("Serial port is not open")
        written = self.ser.write(data)
        if written != len(data):
            raise FirmwareProtocolError(f"Incomplete write: {written}/{len(data)} bytes")

    def _read_exact(self, n: int) -> bytes:
        if not self.ser or not self.ser.is_open:
            raise FirmwareProtocolError("Serial port is not open")
        out = bytearray()
        while len(out) < n:
            chunk = self.ser.read(n - len(out))
            if not chunk:
                raise FirmwareProtocolError("Read timeout waiting for radio response")
            out.extend(chunk)
        return bytes(out)

    def _read_until_start(self, *, max_scan: int = 8192) -> None:
        """
        Scan stream until 0xAA is found (discarding any noise).

        Important: some radios go silent for a bit between phases (especially right
        after the raw PROGRAM/UPDATE handshake). Treat empty reads as "keep waiting"
        up to an overall deadline, rather than failing immediately.
        """
        if not self.ser or not self.ser.is_open:
            raise FirmwareProtocolError("Serial port is not open")
        deadline = time.time() + max(3.0, float(self.timeout) * 4.0)
        scanned = 0
        while scanned < max_scan:
            if time.time() >= deadline:
                raise FirmwareProtocolError("Read timeout waiting for packet start")
            b = self.ser.read(1)
            if not b:
                continue
            scanned += 1
            if b == b"\xAA":
                return
        raise FirmwareProtocolError("Failed to find packet start byte 0xAA")

    def read_packet(self) -> VendorPacket:
        self._read_until_start()
        hdr = self._read_exact(4)  # cmd, cmdArgs, len_hi, len_lo
        cmd = hdr[0]
        cmd_args = hdr[1]
        data_len = (hdr[2] << 8) | hdr[3]
        data = self._read_exact(data_len)
        crc = self._read_exact(2)
        end = self._read_exact(1)
        raw = b"\xAA" + hdr + data + crc + end
        return unpack_vendor_packet(raw)

    def handshake(self) -> None:
        """
        Raw serial handshake (not packet framed):
          PROGRAM + model_tag + 0x55, expect 0x06; UPDATE, expect 0x06
        """
        if not self.ser or not self.ser.is_open:
            raise FirmwareProtocolError("Serial port is not open")
        # Vendor EXE retries handshake a handful of times; serial timing can be finicky.
        last_exc: Optional[BaseException] = None
        for attempt in range(1, self.retries + 1):
            try:
                self.ser.reset_input_buffer()
                self._write(b"PROGRAM" + self.model_tag + b"U")
                ack = self._read_exact(1)
                if ack != b"\x06":
                    raise FirmwareProtocolError(f"Handshake phase1 expected ACK 0x06, got {ack.hex()}")
                self._write(b"UPDATE")
                ack2 = self._read_exact(1)
                if ack2 != b"\x06":
                    raise FirmwareProtocolError(f"Handshake phase2 expected ACK 0x06, got {ack2.hex()}")

                # BootHelper.HandShake_0() sleeps 20ms before proceeding.
                time.sleep(0.02)
                # Discard any stray bytes before moving into framed mode.
                try:
                    self.ser.reset_input_buffer()
                except Exception:
                    pass
                return
            except BaseException as exc:
                last_exc = exc
                if attempt >= self.retries:
                    break
                time.sleep(0.08)
        raise FirmwareProtocolError(f"Handshake failed after {self.retries} attempts: {last_exc}")

    def _send_packet_with_retry(
        self,
        cmd: int,
        cmd_args: int,
        data: bytes,
        *,
        log_cb: Optional[Callable[[str], None]] = None,
    ) -> VendorPacket:
        pkt = pack_vendor_packet(cmd, cmd_args, data)
        last_exc: Optional[BaseException] = None

        for attempt in range(1, self.retries + 1):
            try:
                if not self.ser or not self.ser.is_open:
                    raise FirmwareProtocolError("Serial port is not open")
                self._write(pkt)
                resp = self.read_packet()

                # Vendor tool treats CommandArgs == 6 as success indicator.
                if resp.cmd_args == 6:
                    return resp

                # Otherwise resp.cmd is an error code.
                if resp.cmd == self.ERR_DATA_CHECK:
                    if log_cb:
                        log_cb(f"Radio reported data check error (226); retrying attempt {attempt}/{self.retries}")
                    continue

                err_map = {
                    self.ERR_HANDSHAKE_CODE: "handshake code error",
                    self.ERR_DATA_CHECK: "data check error",
                    self.ERR_ADDRESS: "address error",
                    self.ERR_FLASH_WRITE: "flash write error",
                    self.ERR_COMMAND: "command error",
                }
                desc = err_map.get(resp.cmd, "unknown error")
                raise FirmwareProtocolError(f"Radio error cmd={resp.cmd} ({desc}), cmd_args={resp.cmd_args}")
            except BaseException as exc:
                last_exc = exc
                if attempt >= self.retries:
                    break
                if log_cb:
                    log_cb(f"Retry {attempt}/{self.retries - 1} for cmd={cmd}: {exc}")
                time.sleep(0.06)

        raise FirmwareProtocolError(f"Command cmd={cmd} failed after {self.retries} attempts: {last_exc}")

    def _enter_bootloader(self, *, log_cb: Optional[Callable[[str], None]] = None) -> None:
        """
        Enter bootloader framed-mode and perform the framed BOOTLOADER handshake.

        Vendor EXE has two entry behaviors:
        - Normal path: send cmd=66 (into boot) then cmd=1 data="BOOTLOADER"
        - PTT-pressed path: skip cmd=66 and start at cmd=1 directly

        Some devices appear to ACK the raw PROGRAM/UPDATE handshake but never
        respond to cmd=66; in that case we fall back to the cmd=1-only path.
        """
        # Some devices need a little time after raw handshake before responding to framed packets.
        time.sleep(0.05)
        try:
            if self.ser:
                self.ser.reset_input_buffer()
            self._send_packet_with_retry(self.CMD_INTO_BOOT, 0, b"", log_cb=log_cb)
        except FirmwareProtocolError as exc:
            # If the device never responds with framed packets, cmd=66 will time out waiting
            # for start byte 0xAA. Try the EXE's alternate path (cmd=1 only).
            if log_cb:
                log_cb(f"cmd 66 failed ({exc}); falling back to cmd 1 BOOTLOADER only")
        self._send_packet_with_retry(self.CMD_HANDSHAKE, 0, b"BOOTLOADER", log_cb=log_cb)

    @staticmethod
    def _bf_lengths_for_vendor(bf_blob: bytes) -> Tuple[int, int]:
        """Return (region1_len, region2_len) with safety normalization for region_count==1."""
        h = parse_bf_header(bf_blob)
        region1_len = int(h.firmware_len)
        region2_len = int(h.data_len) if h.region_count == 2 else 0
        if h.region_count == 1:
            region2_len = 0
        return region1_len, region2_len

    def send_bf(
        self,
        bf_blob: bytes,
        *,
        progress_cb: Optional[Callable[[int, int], None]] = None,
        log_cb: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, int]:
        """
        Send a wrapped .BF image using vendor update flow.

        NOTE: This transmits BF payload bytes as-is (no decrypt/re-encrypt).
        """
        region1_len, region2_len = self._bf_lengths_for_vendor(bf_blob)
        if len(bf_blob) < 16 + region1_len + region2_len:
            raise FirmwareToolError("BF file truncated relative to header lengths")

        pkg1 = (region1_len + PACKAGE_SIZE - 1) // PACKAGE_SIZE
        pkg2 = (region2_len + PACKAGE_SIZE - 1) // PACKAGE_SIZE
        total_pkgs = pkg1 + pkg2
        total_bytes = total_pkgs * PACKAGE_SIZE

        def _update_progress(done_pkgs: int) -> None:
            if progress_cb:
                progress_cb(done_pkgs * PACKAGE_SIZE, total_bytes)

        if log_cb:
            log_cb(f"BF lengths: region1={region1_len}B ({pkg1}x1024), region2={region2_len}B ({pkg2}x1024)")

        # Enter framed boot mode + framed handshake for bootloader update stream.
        self._enter_bootloader(log_cb=log_cb)

        # Region 1.
        self._send_packet_with_retry(self.CMD_UPDATE_DATA_PACKAGES, 0, bytes([pkg1 & 0xFF]), log_cb=log_cb)
        done = 0
        base1 = 16
        for i in range(pkg1):
            off = base1 + i * PACKAGE_SIZE
            chunk = bf_blob[off : off + PACKAGE_SIZE]
            if len(chunk) < PACKAGE_SIZE:
                chunk = chunk + (b"\xFF" * (PACKAGE_SIZE - len(chunk)))
            self._send_packet_with_retry(self.CMD_UPDATE, i & 0xFF, chunk, log_cb=log_cb)
            done += 1
            _update_progress(done)

        # Region 2 count is always sent in vendor flow (even if 0).
        self._send_packet_with_retry(self.CMD_UPDATE_DATA_PACKAGES2, 0, bytes([pkg2 & 0xFF]), log_cb=log_cb)
        base2 = 16 + region1_len
        for i in range(pkg2):
            off = base2 + i * PACKAGE_SIZE
            chunk = bf_blob[off : off + PACKAGE_SIZE]
            if len(chunk) < PACKAGE_SIZE:
                chunk = chunk + (b"\xFF" * (PACKAGE_SIZE - len(chunk)))
            self._send_packet_with_retry(self.CMD_UPDATE, i & 0xFF, chunk, log_cb=log_cb)
            done += 1
            _update_progress(done)

        self._send_packet_with_retry(self.CMD_UPDATE_END, 0, b"", log_cb=log_cb)
        _update_progress(total_pkgs)
        if log_cb:
            log_cb("Vendor update end sent (cmd 69)")

        return {
            "region1_len": region1_len,
            "region2_len": region2_len,
            "packages1": pkg1,
            "packages2": pkg2,
            "packages_total": total_pkgs,
        }


class LegacyFirmwareFlasher:
    """
    Host-side firmware flasher for K-plug bootloader style exchanges.

    This implementation follows common bootloader patterns used by UV-5RM-family
    tooling:
    - handshake magic: b'\\x50\\xBB' or b'PROGRAMBFNORMALU'
    - ACK byte: 0x06
    - chunked payload writes with 32-bit address + simple checksum
    """

    def __init__(
        self,
        port: str,
        *,
        baudrate: int = 9600,
        timeout: float = 1.0,
        chunk_size: int = 256,
        retries: int = 3,
    ):
        if chunk_size < 64 or chunk_size > 256:
            raise FirmwareToolError("chunk_size must be between 64 and 256")
        if serial is None:
            raise FirmwareToolError("PySerial is required for flashing")

        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.chunk_size = chunk_size
        self.retries = retries
        self.ser = None

    def open(self) -> None:
        self.ser = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            bytesize=8,
            parity="N",
            stopbits=1,
            timeout=self.timeout,
            write_timeout=self.timeout,
            rtscts=False,
        )
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()

    def close(self) -> None:
        if self.ser and self.ser.is_open:
            self.ser.close()

    def __enter__(self) -> "LegacyFirmwareFlasher":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _write(self, data: bytes) -> None:
        if not self.ser or not self.ser.is_open:
            raise FirmwareProtocolError("Serial port is not open")
        written = self.ser.write(data)
        if written != len(data):
            raise FirmwareProtocolError(f"Incomplete write: {written}/{len(data)} bytes")

    def _read(self, length: int = 1) -> bytes:
        if not self.ser or not self.ser.is_open:
            raise FirmwareProtocolError("Serial port is not open")
        data = self.ser.read(length)
        if len(data) < length:
            raise FirmwareProtocolError("Read timeout waiting for radio response")
        return data

    def _wait_ack(self) -> None:
        ack = self._read(1)
        if ack != b"\x06":
            raise FirmwareProtocolError(f"Expected ACK 0x06, got {ack.hex()}")

    def handshake(self, magic_candidates: Sequence[bytes] = (b"\x50\xBB", b"PROGRAMBFNORMALU")) -> bytes:
        """Try multiple known handshake magics and return the one that succeeded."""
        if not self.ser or not self.ser.is_open:
            raise FirmwareProtocolError("Serial port is not open")

        errors: List[str] = []
        for magic in magic_candidates:
            try:
                self.ser.reset_input_buffer()
                self._write(magic)
                self._wait_ack()
                if magic == b"PROGRAMBFNORMALU":
                    self._write(b"D")
                return magic
            except Exception as exc:
                errors.append(f"{magic!r}: {exc}")
                time.sleep(0.08)
        raise FirmwareProtocolError("Handshake failed for all candidates: " + "; ".join(errors))

    @staticmethod
    def build_write_frame(address: int, chunk: bytes) -> bytes:
        """
        Build legacy write frame:
        [ 'W' | addr_be_u32 | len_be_u16 | payload | sum8(addr+len+payload) ]
        """
        if len(chunk) > 0xFFFF:
            raise FirmwareToolError("Chunk too large")
        head = b"W" + struct.pack(">I", address) + struct.pack(">H", len(chunk))
        checksum = sum(head[1:] + chunk) & 0xFF
        return head + chunk + bytes([checksum])

    def send_chunk(self, address: int, chunk: bytes) -> None:
        frame = self.build_write_frame(address, chunk)
        self._write(frame)
        self._wait_ack()

    def finalize(self) -> None:
        self._write(b"OVER")
        try:
            self._wait_ack()
        except Exception:
            # Some bootloaders reboot immediately and do not ACK finalize.
            pass

    def flash_firmware(
        self,
        firmware: bytes,
        *,
        start_address: int = FW_FLASH_BASE,
        progress_cb: Optional[Callable[[int, int], None]] = None,
        log_cb: Optional[Callable[[str], None]] = None,
    ) -> None:
        if len(firmware) > FW_FLASH_LIMIT:
            raise FirmwareToolError(
                f"Firmware too large: {len(firmware)} bytes (limit {FW_FLASH_LIMIT} bytes from 0x{FW_FLASH_BASE:08X})"
            )

        used_magic = self.handshake()
        if log_cb:
            log_cb(f"Handshake OK: {used_magic!r}")

        sent = 0
        total = len(firmware)
        while sent < total:
            chunk = firmware[sent : sent + self.chunk_size]
            address = start_address + sent
            for attempt in range(1, self.retries + 1):
                try:
                    self.send_chunk(address, chunk)
                    break
                except Exception as exc:
                    if attempt >= self.retries:
                        raise FirmwareProtocolError(
                            f"Write failed at 0x{address:08X}, len={len(chunk)} after {attempt} attempts: {exc}"
                        ) from exc
                    if log_cb:
                        log_cb(f"Retry {attempt}/{self.retries - 1} at 0x{address:08X}: {exc}")
                    time.sleep(0.06)

            sent += len(chunk)
            if progress_cb:
                progress_cb(sent, total)

        self.finalize()
        if log_cb:
            log_cb("Finalize command sent")


def analyze_firmware_vector_table(
    firmware: bytes,
    *,
    start_address: int = FW_FLASH_BASE,
    flash_limit: int = FW_FLASH_LIMIT,
) -> Dict[str, str]:
    """
    Heuristic validation for Cortex-M images.

    This does NOT read the radio. It only checks that the image *looks like*
    it is meant to live at `start_address`:
    - vector[0] initial SP should be in SRAM (0x2000_0000..0x2008_0000, broad)
    - vector[1] reset handler should be Thumb (LSB=1) and point into flash
      near the programmed region.
    """
    res: Dict[str, str] = {
        "plausible": "no",
        "reason": "",
        "start_address": f"0x{start_address:08X}",
        "image_len": str(len(firmware)),
    }
    if len(firmware) < 8:
        res["reason"] = "image too small to contain a vector table"
        return res

    sp, reset = struct.unpack_from("<II", firmware, 0)
    reset_addr = reset & ~1
    res["sp"] = f"0x{sp:08X}"
    res["reset"] = f"0x{reset:08X}"
    res["reset_addr"] = f"0x{reset_addr:08X}"
    res["reset_thumb"] = "yes" if (reset & 1) else "no"

    # Broad SRAM range (device-specific SRAM sizes vary).
    sp_ok = 0x20000000 <= sp <= 0x20080000
    if not sp_ok:
        res["reason"] = "initial SP not in expected SRAM range (0x20000000..0x20080000)"
        return res

    if (reset & 1) == 0:
        res["reason"] = "reset handler is not Thumb (LSB is 0)"
        return res

    max_span = min(len(firmware), flash_limit)
    low = start_address
    high = start_address + max_span
    if not (low <= reset_addr < high):
        res["reason"] = f"reset handler not within [{low:#010x}, {high:#010x})"
        return res

    res["plausible"] = "yes"
    res["reason"] = "vector table looks consistent for start address"
    return res


def flash_firmware_serial(
    port: str,
    firmware: bytes,
    *,
    baudrate: int = 9600,
    timeout: float = 1.0,
    chunk_size: int = 256,
    retries: int = 3,
    start_address: int = FW_FLASH_BASE,
    dry_run: bool = False,
    probe_handshake: bool = False,
    progress_cb: Optional[Callable[[int, int], None]] = None,
    log_cb: Optional[Callable[[str], None]] = None,
) -> Dict[str, str]:
    """Top-level firmware flash helper used by UI/CLI."""
    if len(firmware) > FW_FLASH_LIMIT:
        raise FirmwareToolError(
            f"Firmware too large: {len(firmware)} bytes (limit {FW_FLASH_LIMIT} bytes from 0x{FW_FLASH_BASE:08X})"
        )

    vt = analyze_firmware_vector_table(firmware, start_address=start_address, flash_limit=FW_FLASH_LIMIT)

    if dry_run:
        used_magic = None
        if probe_handshake:
            with LegacyFirmwareFlasher(
                port=port,
                baudrate=baudrate,
                timeout=timeout,
                chunk_size=chunk_size,
                retries=retries,
            ) as flasher:
                used_magic = flasher.handshake()
                if log_cb:
                    log_cb(f"Handshake OK (probe-only): {used_magic!r}")
        if progress_cb:
            progress_cb(len(firmware), len(firmware))
        return {
            "mode": "dry-run",
            "port": port,
            "baudrate": str(baudrate),
            "size": str(len(firmware)),
            "start_address": f"0x{start_address:08X}",
            **({"handshake_magic": repr(used_magic)} if used_magic is not None else {}),
            "vector_table_plausible": vt.get("plausible", "no"),
            "vector_table_reason": vt.get("reason", ""),
        }

    with LegacyFirmwareFlasher(
        port=port,
        baudrate=baudrate,
        timeout=timeout,
        chunk_size=chunk_size,
        retries=retries,
    ) as flasher:
        flasher.flash_firmware(
            firmware,
            start_address=start_address,
            progress_cb=progress_cb,
            log_cb=log_cb,
        )
    return {
        "mode": "write",
        "port": port,
        "baudrate": str(baudrate),
        "size": str(len(firmware)),
        "start_address": f"0x{start_address:08X}",
        "vector_table_plausible": vt.get("plausible", "no"),
        "vector_table_reason": vt.get("reason", ""),
    }


def flash_vendor_bf_serial(
    port: str,
    bf_blob: bytes,
    *,
    baudrate: int = 115200,
    timeout: float = 1.0,
    retries: int = 5,
    model_tag: bytes = b"BFNORMAL",
    firmware_type: Optional[str] = None,
    allow_small_firmware: bool = False,
    min_firmware_bytes: int = 10 * 1024,
    dry_run: bool = False,
    probe_handshake: bool = False,
    probe_packets: bool = False,
    progress_cb: Optional[Callable[[int, int], None]] = None,
    log_cb: Optional[Callable[[str], None]] = None,
) -> Dict[str, str]:
    """
    Vendor-protocol firmware flash helper for wrapped .BF images.

    - In dry-run mode, it parses BF header and reports package counts.
    - If `probe_handshake=True`, it opens the port and performs the raw
      PROGRAM/UPDATE handshake (expects ACKs).
    - If `probe_packets=True`, it additionally sends vendor framed packets
      (cmd 66 and cmd 1 "BOOTLOADER") and verifies a valid framed response.
    """
    region1_len, region2_len = VendorFirmwareFlasher._bf_lengths_for_vendor(bf_blob)
    pkg1 = (region1_len + PACKAGE_SIZE - 1) // PACKAGE_SIZE
    pkg2 = (region2_len + PACKAGE_SIZE - 1) // PACKAGE_SIZE
    total_pkgs = pkg1 + pkg2
    total_bytes = total_pkgs * PACKAGE_SIZE

    if progress_cb:
        progress_cb(0, total_bytes)

    # Safety checks:
    # - reject suspiciously small images unless explicitly allowed
    # - if the decrypted payload looks like a dumper, require firmware_type="dumper"
    try:
        fw_for_analysis, _data_for_analysis, _hdr = unwrap_bf_bytes(bf_blob, decrypt_firmware=True, decrypt_data=False)
    except Exception as exc:
        raise FirmwareToolError(f"Failed to unwrap BF for analysis: {exc}")

    if len(fw_for_analysis) < int(min_firmware_bytes) and not allow_small_firmware:
        raise FirmwareToolError(
            f"Refusing to flash very small firmware payload ({len(fw_for_analysis)} bytes). "
            f"If this is intentional (e.g. a dumper), pass allow_small_firmware=True and "
            f'firmware_type="dumper".'
        )

    dumper_signatures = [b"FLASH DUMPER", b"BD4VOW", b"FLASHDUMPER", b"DUMPER BY", b"BOOTLOADER ***"]
    fw_upper = fw_for_analysis.upper()
    matched = [s for s in dumper_signatures if s in fw_upper]
    if matched:
        if log_cb:
            log_cb(f"Warning: firmware contains dumper-like signatures: {[m.decode('ascii', 'ignore') for m in matched]}")
        if firmware_type != "dumper":
            raise FirmwareToolError(
                "This firmware appears to be a dumper image. Refusing to flash unless "
                'firmware_type="dumper" is explicitly provided.'
            )

    if dry_run:
        handshake_ok = "no"
        packets_ok = "no"
        if probe_handshake or probe_packets:
            with VendorFirmwareFlasher(
                port=port,
                baudrate=baudrate,
                timeout=timeout,
                retries=retries,
                model_tag=model_tag,
            ) as fl:
                if probe_handshake:
                    fl.handshake()
                    handshake_ok = "yes"
                    if log_cb:
                        log_cb("Vendor handshake OK (probe-only)")
                if probe_packets:
                    # These packets should not transmit any firmware data packages.
                    # If probe_handshake is False, we still attempt framed entry: some devices
                    # may already be in framed bootloader mode where raw handshake is ignored.
                    fl._enter_bootloader(log_cb=log_cb)
                    packets_ok = "yes"
                    if log_cb:
                        log_cb("Vendor framed packet probe OK (bootloader entry + cmd 1)")
        if progress_cb:
            progress_cb(total_bytes, total_bytes)
        return {
            "mode": "dry-run",
            "port": port,
            "baudrate": str(baudrate),
            "region1_len": str(region1_len),
            "region2_len": str(region2_len),
            "packages1": str(pkg1),
            "packages2": str(pkg2),
            "packages_total": str(total_pkgs),
            "payload_bytes_total": str(total_bytes),
            "probe_handshake": "yes" if probe_handshake else "no",
            "handshake_ok": handshake_ok,
            "probe_packets": "yes" if probe_packets else "no",
            "packets_ok": packets_ok,
        }

    with VendorFirmwareFlasher(
        port=port,
        baudrate=baudrate,
        timeout=timeout,
        retries=retries,
        model_tag=model_tag,
    ) as fl:
        fl.handshake()
        info = fl.send_bf(bf_blob, progress_cb=progress_cb, log_cb=log_cb)

    return {
        "mode": "write",
        "port": port,
        "baudrate": str(baudrate),
        "region1_len": str(info["region1_len"]),
        "region2_len": str(info["region2_len"]),
        "packages1": str(info["packages1"]),
        "packages2": str(info["packages2"]),
        "packages_total": str(info["packages_total"]),
        "payload_bytes_total": str(info["packages_total"] * PACKAGE_SIZE),
    }


def firmware_from_upload_bytes(
    blob: bytes,
    *,
    wrapped_bf: bool,
    decrypt_bf_firmware: bool = True,
) -> Tuple[bytes, Dict[str, str]]:
    """Normalize firmware payload from either raw BIN or wrapped BF upload."""
    if not wrapped_bf:
        return blob, {"source": "bin", "size": str(len(blob))}
    fw, data, header = unwrap_bf_bytes(blob, decrypt_firmware=decrypt_bf_firmware, decrypt_data=False)
    meta = {
        "source": "bf",
        "region_count": str(header.region_count),
        "firmware_len": str(header.firmware_len),
        "data_len": str(header.data_len),
        "data_present": "yes" if bool(data) else "no",
    }
    return fw, meta


def suggest_manual_dumper_flash_steps() -> List[str]:
    """Fallback instructions when dumper flashing cannot be automated."""
    return [
        "Connect SWD probe to AT32F421 target (3V3, GND, SWDIO, SWCLK).",
        "Flash dumper firmware (ELF/BIN/BF-converted payload) using pyOCD/OpenOCD.",
        "Power-cycle radio into normal mode and connect K-plug serial adapter.",
        "Run dumper monitor at 115200 baud and capture BOOTLOADER/SYS BOOTLOADER sections.",
    ]
