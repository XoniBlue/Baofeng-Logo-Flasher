"""
UV-5RM Radio Protocol Layer

High-level protocol operations for Baofeng UV-5R/UV-5RM radios.
Extracted from CHIRP integration for standalone use.

This module provides:
- Model identification and configuration
- Firmware version detection
- Full clone download/upload
- Block-level read/write with proper addressing
- Dropped-byte detection and workaround
"""

import logging
from typing import Optional, Tuple, List, Dict
from dataclasses import dataclass

from .uv5rm_transport import (
    UV5RMTransport,
    RadioTransportError,
    RadioNoContact,
    RadioBlockError,
)

# Import model registry for unified detection
try:
    from baofeng_logo_flasher.models import detect_model as registry_detect_model, get_model
    _HAS_REGISTRY = True
except ImportError:
    _HAS_REGISTRY = False

logger = logging.getLogger(__name__)


@dataclass
class RadioModel:
    """Definition of a Baofeng radio model"""
    vendor: str
    model: str
    variant: Optional[str] = None
    baud_rate: int = 9600
    mem_size: int = 0x1808
    has_aux_block: bool = True
    fw_ver_start: int = 0x1838
    fw_ver_stop: int = 0x1846
    magic_bytes: Optional[List[bytes]] = None

    def __post_init__(self):
        if self.magic_bytes is None:
            self.magic_bytes = []


class UV5RMProtocol:
    """
    High-level radio protocol handler.

    Manages firmware detection, memory mapping, and clone operations.

    Supported models:
    - Baofeng UV-5R (original & BFB291+)
    - Baofeng UV-82, UV-6, F-11
    - Radioddity 82X3
    - Other UV5R-based variants

    Example:
        radio = UV5RMProtocol(transport)
        model_info = radio.identify_radio()
        clone_data = radio.download_clone()
        radio.upload_clone(clone_data)
    """

    # Magic bytes for various models
    MAGIC_BYTES = {
        'UV5R_ORIG': b"\x50\xBB\xFF\x01\x25\x98\x4D",
        'UV5R_291': b"\x50\xBB\xFF\x20\x12\x07\x25",
        'F11': b"\x50\xBB\xFF\x13\xA1\x11\xDD",
        'UV82': b"\x50\xBB\xFF\x20\x13\x01\x05",
        'UV6': b"\x50\xBB\xFF\x20\x12\x08\x23",
        'UV6_ORIG': b"\x50\xBB\xFF\x12\x03\x98\x4D",
        'A58': b"\x50\xBB\xFF\x20\x14\x04\x13",
        'UV5G': b"\x50\xBB\xFF\x20\x12\x06\x25",
    }

    # Base type identifiers (found in firmware version string)
    BASE_TYPES = {
        'UV5R': [b"BFS", b"BFB", b"N5R-2", b"N5R2", b"N5RV", b"BTS", b"D5R2", b"B5R2"],
        'F11': [b"USA"],
        'UV82': [b"US2S2", b"B82S", b"BF82", b"N82-2", b"N822"],
        'UV6': [b"BF1", b"UV6"],
        'KT980HP': [b"BFP3V3 B"],
        'F8HP': [b"BFP3V3 F", b"N5R-3", b"N5R3", b"F5R3", b"BFT", b"N5RV"],
        'UV82HP': [b"N82-3", b"N823", b"N5R2"],
        'UV82X3': [b"HN5RV01"],
    }

    def __init__(self, transport: UV5RMTransport):
        """
        Initialize protocol handler.

        Args:
            transport: UV5RMTransport instance (must be open)
        """
        self.transport = transport
        self._radio_ident: Optional[bytes] = None
        self._radio_version: Optional[bytes] = None
        self._has_dropped_byte: bool = False
        self._model: Optional[RadioModel] = None

    @property
    def radio_ident(self) -> Optional[bytes]:
        """Last identified radio ident (8 bytes)"""
        return self._radio_ident

    @property
    def radio_version(self) -> Optional[bytes]:
        """Last detected firmware version string"""
        return self._radio_version

    @property
    def has_dropped_byte(self) -> bool:
        """True if radio has dropped-byte issue (requires workaround)"""
        return self._has_dropped_byte

    def identify_radio(
        self,
        magic_sequence: Optional[List[bytes]] = None,
    ) -> Dict:
        """
        Identify radio and determine configuration.

        Attempts handshake with provided magic bytes (or all known sequences).
        Detects firmware version and any hardware quirks.

        Args:
            magic_sequence: List of magic byte sequences to try (optional)
                If None, tries all known sequences in order.

        Returns:
            Dict with keys:
                - ident: Radio identification (8 bytes)
                - version: Firmware version string
                - model: Detected model name
                - has_dropped_byte: True if workaround needed
                - is_original_fw: True if BFB<291 (legacy firmware)

        Raises:
            RadioNoContact: If radio does not respond to any magic bytes
        """
        if not self.transport.ser or not self.transport.ser.is_open:
            raise RadioTransportError("Transport not open")

        # Build magic sequence
        if magic_sequence is None:
            magic_sequence = [
                self.MAGIC_BYTES['UV5R_291'],    # Try BFB291+ first
                self.MAGIC_BYTES['UV5R_ORIG'],
                self.MAGIC_BYTES['UV82'],
                self.MAGIC_BYTES['UV6'],
                self.MAGIC_BYTES['F11'],
                self.MAGIC_BYTES['A58'],
                self.MAGIC_BYTES['UV5G'],
                self.MAGIC_BYTES['UV6_ORIG'],
            ]

        # Try each magic sequence
        last_error = None
        for magic in magic_sequence:
            try:
                logger.info(f"Trying magic: {magic.hex().upper()}")
                ident = self.transport.handshake(magic, retry_count=0)
                self._radio_ident = ident
                break
            except RadioNoContact as e:
                last_error = e
                continue
        else:
            raise RadioNoContact(
                f"Radio did not respond to any magic bytes. Last error: {last_error}"
            )

        # Get firmware version and detect quirks
        version, has_dropped_byte = self._get_firmware_version()
        self._radio_version = version
        self._has_dropped_byte = has_dropped_byte

        # Determine firmware generation
        is_original_fw = False
        if b'BFB' in version:
            try:
                idx = version.index(b"BFB") + 3
                fw_num = int(version[idx:idx + 3])
                is_original_fw = (fw_num < 291)
            except (ValueError, IndexError):
                is_original_fw = False

        # Detect model
        model_name = self._detect_model(version)

        logger.info(
            f"Identified: {model_name}, "
            f"FW={version.decode('latin-1', errors='ignore').strip()}, "
            f"dropped_byte={has_dropped_byte}"
        )

        return {
            'ident': ident,
            'version': version,
            'model': model_name,
            'has_dropped_byte': has_dropped_byte,
            'is_original_fw': is_original_fw,
        }

    def _get_firmware_version(self) -> Tuple[bytes, bool]:
        """
        Detect radio firmware version and dropped-byte issue.

        Returns:
            Tuple of (version_string, has_dropped_byte_issue)
        """
        try:
            # Read warm-up block (0x1E80) - works around issue on new radios
            block0 = self.transport.read_block(0x1E80, 0x40, first_block=True)

            # Read version block (0x1EC0)
            block1 = self.transport.read_block(0x1EC0, 0x40, first_block=False)

            # Get version (bytes 48-62 in the block)
            version = block1[48:62]

            # Check for dropped byte at 0x1FCF
            block2 = self.transport.read_block(0x1FC0, 0x40, first_block=False)
            dropped_byte = (block2[15:16] == b"\xFF")

            logger.debug(
                f"Version: {version}, Dropped byte: {dropped_byte}"
            )

            return version, dropped_byte

        except (RadioTransportError, IndexError) as e:
            raise RadioBlockError(f"Firmware detection failed: {e}")

    def _detect_model(self, version: bytes) -> str:
        """Detect radio model from firmware version string.

        Uses the model registry if available, falls back to internal matching.
        """
        # Try registry first if available
        if _HAS_REGISTRY:
            config = registry_detect_model(version_bytes=version)
            if config:
                return config.name

        # Fallback to internal matching
        for model_name, base_types in self.BASE_TYPES.items():
            for base_type in base_types:
                if base_type in version:
                    return model_name
        return "Unknown"

    def download_clone(self) -> bytes:
        """
        Download complete memory image from radio.

        Performs:
        1. Identify radio (if not already done)
        2. Read main memory (0x0000 - 0x1808)
        3. Read auxiliary memory (0x1EC0 - 0x2000, with dropped-byte workaround)
        4. Prepend radio identification

        Returns:
            Complete memory image (6150 - 6408 bytes depending on model)

        Raises:
            RadioBlockError: If read fails
        """
        logger.info("Starting clone download...")

        # Ensure we have ID
        if self._radio_ident is None:
            self.identify_radio()

        data = self._radio_ident if self._radio_ident else b""

        # Read main memory (0x0000 - 0x1808 in 0x40-byte blocks)
        logger.info("Reading main memory...")
        for addr in range(0x0000, 0x1800, 0x40):
            block = self.transport.read_block(addr, 0x40, first_block=(addr == 0x0000))
            data += block

            # Progress
            pct = (addr / 0x1800) * 100
            if addr % 0x100 == 0:
                logger.debug(f"Main memory: {pct:.1f}%")

        # Read auxiliary memory (0x1EC0 - 0x2000)
        logger.info("Reading auxiliary memory...")

        if self._has_dropped_byte:
            # Workaround: use smaller blocks for final range
            # Read 0x1EC0 - 0x1FC0 in 0x40-byte blocks
            for addr in range(0x1EC0, 0x1FC0, 0x40):
                block = self.transport.read_block(addr, 0x40)
                data += block

            # Read 0x1FC0 - 0x2000 in 0x10-byte blocks
            for addr in range(0x1FC0, 0x2000, 0x10):
                block = self.transport.read_block(addr, 0x10)
                data += block
        else:
            # Standard: read entire aux range in 0x40-byte blocks
            for addr in range(0x1EC0, 0x2000, 0x40):
                block = self.transport.read_block(addr, 0x40)
                data += block

        logger.info(f"Download complete: {len(data)} bytes")
        return data

    def upload_clone(self, image_data: bytes) -> None:
        """
        Upload memory image to radio.

        Performs:
        1. Identify radio (if not already done)
        2. Verify image compatibility
        3. Write main memory (0x0000 - 0x1808)
        4. Write auxiliary memory (0x1EC0 - 0x2000)

        Args:
            image_data: Complete memory image (must be valid for radio model)

        Raises:
            RadioBlockError: If write fails or image incompatible
            ValueError: If image format invalid
        """
        if len(image_data) < 0x1808:
            raise ValueError(
                f"Image too small: {len(image_data)} bytes "
                f"(minimum {0x1808})"
            )

        logger.info(f"Starting clone upload ({len(image_data)} bytes)...")

        # Ensure we have ID
        if self._radio_ident is None:
            self.identify_radio()

        # Extract image ident and main memory
        image_ident = image_data[0:8]
        image_main = image_data[8:8 + 0x1800]
        image_aux = image_data[8 + 0x1800:] if len(image_data) > (8 + 0x1800) else b""

        # Write main memory (0x0000 - 0x1800 in 0x10-byte chunks)
        logger.info("Writing main memory...")
        for addr in range(0x0000, 0x1800, 0x10):
            chunk = image_main[addr:addr + 0x10]
            self.transport.write_block(addr, chunk)

            # Progress
            pct = (addr / 0x1800) * 100
            if addr % 0x100 == 0:
                logger.debug(f"Main memory: {pct:.1f}%")

        # Write auxiliary memory if present
        if image_aux:
            logger.info("Writing auxiliary memory...")

            if self._has_dropped_byte:
                # Workaround: use 0x10-byte blocks for sensitive range
                for addr in range(0x1FC0, 0x2000, 0x10):
                    offset = addr - 0x1EC0
                    if offset < len(image_aux):
                        chunk = image_aux[offset:offset + 0x10]
                        self.transport.write_block(addr, chunk)
            else:
                # Standard: use 0x10-byte blocks for all aux memory
                for addr in range(0x1EC0, 0x2000, 0x10):
                    offset = addr - 0x1EC0
                    if offset < len(image_aux):
                        chunk = image_aux[offset:offset + 0x10]
                        self.transport.write_block(addr, chunk)

        logger.info("Upload complete")

    def read_block(self, addr: int, size: int) -> bytes:
        """
        Read a memory block from radio.

        Args:
            addr: Memory address
            size: Number of bytes to read

        Returns:
            Bytes from memory
        """
        return self.transport.read_block(addr, size)

    def write_block(self, addr: int, data: bytes) -> None:
        """
        Write a memory block to radio.

        Args:
            addr: Memory address
            data: Bytes to write
        """
        self.transport.write_block(addr, data)

    def verify_clone(
        self,
        image_data: bytes,
        ranges: Optional[List[Tuple[int, int]]] = None,
    ) -> Dict:
        """
        Verify that radio memory matches image data.

        IMPORTANT: Clone image structure includes 8-byte ident prefix!

        Clone Image Layout:
            Bytes 0-7:    Radio ident (8 bytes, prepended by download_clone)
            Bytes 8+:     Memory dump starting at radio address 0x0000

        So to compare radio address X with image, we read image[X + 8].

        Args:
            image_data: Reference image to verify against (includes 8-byte ident prefix)
            ranges: List of (start, end) address ranges to verify
                    If None, verifies standard memory ranges

        Returns:
            Dict with verification results:
                - verified: True if all ranges match
                - errors: List of mismatches
                - checked_bytes: Total bytes compared
        """
        # Clone image has 8-byte ident prefix (from download_clone)
        IDENT_SIZE = 8

        if ranges is None:
            ranges = [
                (0x0000, 0x1808),  # Main memory
                (0x1EC0, 0x2000),  # Auxiliary memory
            ]

        logger.info(f"Verifying clone data...")

        errors = []
        total_bytes = 0

        for start, end in ranges:
            try:
                for addr in range(start, end, 0x40):
                    size = min(0x40, end - addr)
                    radio_data = self.transport.read_block(addr, size)

                    # Clone image has 8-byte ident prefix, so add IDENT_SIZE to get
                    # the correct offset into the image data for this radio address
                    img_offset = addr + IDENT_SIZE

                    ref_data = image_data[img_offset:img_offset + size]

                    if radio_data != ref_data:
                        errors.append({
                            'address': addr,
                            'size': size,
                            'radio': radio_data.hex(),
                            'reference': ref_data.hex(),
                        })

                    total_bytes += size
            except RadioBlockError as e:
                errors.append({
                    'error': str(e),
                    'range': (start, end),
                })

        verified = len(errors) == 0

        logger.info(
            f"Verification complete: "
            f"verified={verified}, "
            f"errors={len(errors)}, "
            f"bytes_checked={total_bytes}"
        )

        return {
            'verified': verified,
            'errors': errors,
            'checked_bytes': total_bytes,
        }
