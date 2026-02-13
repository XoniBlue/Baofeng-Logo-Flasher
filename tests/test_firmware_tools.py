import pytest


from baofeng_logo_flasher.firmware_tools import (
    FW_FLASH_LIMIT,
    FirmwareToolError,
    analyze_firmware_vector_table,
    unwrap_bf_bytes,
    flash_firmware_serial,
)


def _make_bf_blob(*, region_count: int, firmware: bytes, data_len: int = 0, reserved: bytes = b"\x00" * 7) -> bytes:
    assert len(reserved) == 7
    header = bytearray(16)
    header[0] = region_count
    header[1:5] = len(firmware).to_bytes(4, "big")
    header[5:9] = int(data_len).to_bytes(4, "big")
    header[9:16] = reserved
    return bytes(header) + firmware


def test_unwrap_region_count_1_normalizes_data_len_to_zero():
    fw = b"\x01\x02\x03\x04\x05"
    bf = _make_bf_blob(region_count=1, firmware=fw, data_len=0x9F9F9F9F)
    out_fw, out_data, header = unwrap_bf_bytes(bf, decrypt_firmware=False, decrypt_data=False)
    assert out_fw == fw
    assert out_data == b""
    assert header.region_count == 1
    assert header.firmware_len == len(fw)
    assert header.data_len == 0


def test_unwrap_unsupported_region_count_raises_clear_error():
    fw = b"\xAA" * 8
    bf = _make_bf_blob(region_count=3, firmware=fw, data_len=0)
    with pytest.raises(FirmwareToolError) as ei:
        unwrap_bf_bytes(bf, decrypt_firmware=False, decrypt_data=False)
    assert "region_count=3" in str(ei.value)


def test_flash_firmware_serial_dry_run_enforces_size_limit():
    fw = b"\x00" * (FW_FLASH_LIMIT + 1)
    with pytest.raises(FirmwareToolError):
        flash_firmware_serial(port="dummy", firmware=fw, dry_run=True)


def test_analyze_firmware_vector_table_rejects_too_small():
    info = analyze_firmware_vector_table(b"", start_address=0x08001000, flash_limit=FW_FLASH_LIMIT)
    assert info["plausible"] == "no"
