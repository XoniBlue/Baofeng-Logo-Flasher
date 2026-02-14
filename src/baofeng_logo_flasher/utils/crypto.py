"""
Shared cryptographic/transformation helpers.

Today this is primarily the UV-5RM/5RH-style BF firmware XOR scheme
(symmetric encrypt/decrypt).
"""

from __future__ import annotations


class Crypto:
    """Shared crypto helpers (symmetric transforms)."""

    XOR_KEY1 = b"KDHT"
    XOR_KEY2 = b"RBGI"
    PACKAGE_SIZE = 1024  # 1KB

    @staticmethod
    def xor_crypt_block(data: bytes, key: bytes) -> bytes:
        """
        XOR encrypt/decrypt a block of data with conditional byte handling.

        Bytes are NOT encrypted if:
        - Byte value is 0x00
        - Byte value is 0xFF
        - Byte equals the key byte at that position
        - Byte equals the key byte XOR 0xFF
        """
        out = bytearray(len(data))
        for i, byte in enumerate(data):
            key_byte = key[i % 4]
            if byte not in (0x00, 0xFF, key_byte, key_byte ^ 0xFF):
                out[i] = byte ^ key_byte
            else:
                out[i] = byte
        return bytes(out)

    @classmethod
    def crypt_firmware_payload(cls, data: bytes, key1: bytes | None = None, key2: bytes | None = None) -> bytes:
        """
        Encrypt or decrypt firmware payload using the UV-5RM algorithm.

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

        if key1 is None:
            key1 = cls.XOR_KEY1
        if key2 is None:
            key2 = cls.XOR_KEY2

        package_count, rem = divmod(len(data), cls.PACKAGE_SIZE)
        if rem:
            package_count += 1

        out = bytearray()
        for i in range(package_count):
            start = i * cls.PACKAGE_SIZE
            end = min(start + cls.PACKAGE_SIZE, len(data))
            block = data[start:end]
            if i >= 2 and i < package_count - 2:
                if i % 3 == 1:
                    block = cls.xor_crypt_block(block, key1)
                elif i % 3 == 2:
                    block = cls.xor_crypt_block(block, key2)
            out.extend(block)
        return bytes(out[: len(data)])

