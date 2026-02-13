import pytest


from baofeng_logo_flasher.firmware_tools import (
    crc16_ccitt,
    pack_vendor_packet,
    unpack_vendor_packet,
    wrap_bf_bytes,
    VendorFirmwareFlasher,
)


def test_crc16_ccitt_xmodem_vector_123456789():
    # CRC16-CCITT (poly 0x1021, init 0) commonly known as "XMODEM" variant.
    assert crc16_ccitt(b"123456789") == 0x31C3


def test_vendor_packet_pack_unpack_roundtrip():
    pkt = pack_vendor_packet(1, 0, b"BOOTLOADER")
    assert pkt[:1] == b"\xAA"
    assert pkt[-1:] == b"\xEF"

    parsed = unpack_vendor_packet(pkt)
    assert parsed.cmd == 1
    assert parsed.cmd_args == 0
    assert parsed.data == b"BOOTLOADER"


def test_vendor_bf_lengths_normalize_region2_for_region_count_1():
    # Force a BF with region_count=1 but garbage data_len. Vendor flow should treat region2_len=0.
    fw = b"\x11" * 1234
    bf = wrap_bf_bytes(fw, data=b"", encrypt_firmware=False, encrypt_data=False, reserved=b"\x00" * 7)
    # Mutate header bytes 5..8 to non-zero to simulate bad files.
    bf_mut = bytearray(bf)
    bf_mut[5:9] = (0x9F9F9F9F).to_bytes(4, "big")

    r1, r2 = VendorFirmwareFlasher._bf_lengths_for_vendor(bytes(bf_mut))
    assert r1 == len(fw)
    assert r2 == 0

