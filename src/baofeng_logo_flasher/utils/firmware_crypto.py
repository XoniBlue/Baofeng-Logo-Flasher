"""
UV-5RM Firmware Encryption/Decryption Module

Based on reverse engineering work from:
https://github.com/amoxu/Baofeng-UV-5RM-5RH-RE

The UV-5RM uses a custom XOR encryption scheme for firmware files (.BF format).
This module implements the encryption/decryption algorithm for firmware
modification, which could potentially be used to modify boot logos stored
in the external SPI flash.

Keys and Algorithm:
- XOR_KEY1: "KDHT" (for packages where i % 3 == 1)
- XOR_KEY2: "RBGI" (for packages where i % 3 == 2)
- Package size: 1024 bytes (1KB)
- First 2 packages and last 2 packages are NOT encrypted
- Packages where i % 3 == 0 are NOT encrypted (plaintext)
- Special bytes (0x00, 0xFF, key byte, key ^ 0xFF) are NOT encrypted

Hardware Architecture:
- MCU: AT32F421C8T7 (64KB internal flash, 16KB SRAM)
- External Flash: XMC 25QH16CJIG - 16Mbit (2MB) SPI flash
- RF: BK4819
- Boot logo is stored on the external SPI flash, NOT the MCU flash
- The clone protocol only accesses MCU memory, not external SPI flash

Firmware File Format (.BF):
| Offset | Size | Description |
|--------|------|-------------|
| 0x00 | 1 | Wrapped Region Count (usually 0x02) |
| 0x01 | 4 | Region 1 Length (firmware binary) |
| 0x05 | 4 | Region 2 Length (config data) |
| 0x09 | 7 | Reserved (ignored) |
| 0x10 | Region 1 Length | Encrypted Firmware Binary |
| 0x10 + Region 1 | Region 2 Length | Config data (for SYSTEM BOOTLOADER region) |

Credits:
- Original RE work: Amo (amoxu)
- Python implementation: Pavel (OK2MOP)
"""

import struct
from typing import Tuple, Optional

from .crypto import Crypto


# Re-export for compatibility with older imports/tests.
XOR_KEY1 = Crypto.XOR_KEY1
XOR_KEY2 = Crypto.XOR_KEY2
PACKAGE_SIZE = Crypto.PACKAGE_SIZE


def xor_crypt(data: bytes, key: bytes) -> bytes:
    """
    XOR encrypt/decrypt a block of data with conditional byte handling.

    Bytes are NOT encrypted if:
    - Byte value is 0x00
    - Byte value is 0xFF
    - Byte equals the key byte at that position
    - Byte equals the key byte XOR 0xFF

    Args:
        data: Input data to encrypt/decrypt
        key: 4-byte XOR key (KDHT or RBGI)

    Returns:
        Encrypted/decrypted data
    """
    return Crypto.xor_crypt_block(data, key)


def crypt_firmware(data: bytes, key1: bytes = XOR_KEY1, key2: bytes = XOR_KEY2) -> bytes:
    """
    Encrypt or decrypt firmware data using the UV-5RM algorithm.

    The algorithm is symmetric (same function for encrypt and decrypt).

    Encryption pattern per 3KB cycle:
    - Package i % 3 == 0: Plaintext (no encryption)
    - Package i % 3 == 1: XOR with KEY1 ("KDHT")
    - Package i % 3 == 2: XOR with KEY2 ("RBGI")

    Special cases (always plaintext):
    - First 2 packages (packages 0 and 1)
    - Last 2 packages

    Args:
        data: Firmware binary data
        key1: First XOR key (default: KDHT)
        key2: Second XOR key (default: RBGI)

    Returns:
        Crypted firmware data
    """
    return Crypto.crypt_firmware_payload(data, key1=key1, key2=key2)


def unpack_bf_file(bf_data: bytes, decrypt: bool = True) -> Tuple[bytes, bytes]:
    """
    Unpack a .BF firmware file into its two regions.

    Args:
        bf_data: Raw .BF file contents
        decrypt: Whether to decrypt the regions (default: True)

    Returns:
        Tuple of (firmware_binary, config_data)
    """
    if len(bf_data) < 16:
        raise ValueError("BF file too small (need at least 16 byte header)")

    # Parse header
    header = struct.unpack('>BLL7s', bf_data[:16])
    region_count = header[0]
    region1_size = header[1]
    region2_size = header[2]

    if region_count < 1:
        raise ValueError(f"Invalid region count: {region_count}")

    # Extract regions
    region1_start = 16
    region1_end = region1_start + region1_size
    region1 = bf_data[region1_start:region1_end]

    region2 = b""
    if region_count >= 2 and region2_size > 0:
        region2_start = region1_end
        region2_end = region2_start + region2_size
        region2 = bf_data[region2_start:region2_end]

    # Decrypt if requested
    if decrypt:
        region1 = crypt_firmware(region1)
        if region2:
            region2 = crypt_firmware(region2)

    return region1, region2


def pack_bf_file(firmware: bytes, config: bytes = b"", encrypt: bool = True) -> bytes:
    """
    Pack firmware and config data into a .BF file.

    Args:
        firmware: Firmware binary data
        config: Config data (for SYSTEM BOOTLOADER region)
        encrypt: Whether to encrypt the data (default: True)

    Returns:
        Complete .BF file contents
    """
    # Encrypt if requested
    if encrypt:
        firmware = crypt_firmware(firmware)
        if config:
            config = crypt_firmware(config)

    # Build header
    region_count = 2 if config else 1
    header = struct.pack('>BLL', region_count, len(firmware), len(config))
    header += b'\xff' * 7  # Reserved bytes (ignored by flasher)

    return header + firmware + config


def decrypt_firmware_file(input_path: str, output_path: str) -> None:
    """
    Decrypt a .BF firmware file and save the decrypted firmware binary.

    Args:
        input_path: Path to encrypted .BF file
        output_path: Path for decrypted .bin output
    """
    with open(input_path, 'rb') as f:
        bf_data = f.read()

    firmware, config = unpack_bf_file(bf_data, decrypt=True)

    with open(output_path, 'wb') as f:
        f.write(firmware)

    # Optionally save config separately
    if config:
        config_path = output_path.replace('.bin', '_config.bin')
        with open(config_path, 'wb') as f:
            f.write(config)


def encrypt_firmware_file(input_path: str, output_path: str, config_path: Optional[str] = None) -> None:
    """
    Encrypt a firmware binary and save as .BF file.

    Args:
        input_path: Path to decrypted .bin file
        output_path: Path for encrypted .BF output
        config_path: Optional path to config data
    """
    with open(input_path, 'rb') as f:
        firmware = f.read()

    config = b""
    if config_path:
        with open(config_path, 'rb') as f:
            config = f.read()

    bf_data = pack_bf_file(firmware, config, encrypt=True)

    with open(output_path, 'wb') as f:
        f.write(bf_data)


# Hardware constants for reference
HARDWARE_INFO = {
    "mcu": "AT32F421C8T7",
    "mcu_flash_size": 64 * 1024,  # 64KB internal flash
    "mcu_sram_size": 16 * 1024,   # 16KB SRAM
    "external_flash": "XMC 25QH16CJIG",
    "external_flash_size": 2 * 1024 * 1024,  # 16Mbit = 2MB
    "rf_chip": "BK4819",
    "bootloader_address": 0x08000000,
    "firmware_address": 0x08001000,
    "bootloader_size": 4 * 1024,  # 4KB
    "firmware_max_size": 60 * 1024,  # 60KB
    "system_bootloader_region": 0x1FFFE400,  # Config storage
    "notes": [
        "Boot logos are stored on external SPI flash, NOT MCU flash",
        "Clone protocol only accesses MCU memory via UART",
        "Direct boot logo modification requires firmware-level access",
        "Logo address in SPI flash is undocumented - needs RE work",
    ],
}


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage:")
        print(f"  {sys.argv[0]} decrypt input.BF output.bin")
        print(f"  {sys.argv[0]} encrypt input.bin output.BF [config.bin]")
        sys.exit(1)

    mode = sys.argv[1].lower()

    if mode == "decrypt":
        decrypt_firmware_file(sys.argv[2], sys.argv[3])
        print(f"Decrypted {sys.argv[2]} -> {sys.argv[3]}")
    elif mode == "encrypt":
        config = sys.argv[4] if len(sys.argv) > 4 else None
        encrypt_firmware_file(sys.argv[2], sys.argv[3], config)
        print(f"Encrypted {sys.argv[2]} -> {sys.argv[3]}")
    else:
        print(f"Unknown mode: {mode}")
        sys.exit(1)
