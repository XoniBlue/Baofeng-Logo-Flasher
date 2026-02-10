"""Tests for A5 logo protocol frame and payload construction."""

from PIL import Image

from baofeng_logo_flasher.protocol.logo_protocol import (
    CHUNK_SIZE,
    CONFIG_PAYLOAD,
    SETUP_PAYLOAD,
    build_write_frames,
    chunk_image_data,
    convert_image_to_rgb565,
)


def test_protocol_payload_constants_match_capture_reference() -> None:
    """Config/setup bytes should match captured CPS reference values."""
    assert CONFIG_PAYLOAD == bytes([0x00, 0x00, 0x0C, 0x00, 0x00, 0x01])
    assert SETUP_PAYLOAD == bytes([0x00, 0x00, 0x0C, 0x00])


def test_chunk_image_data_uses_1024_bytes_for_full_logo() -> None:
    """160x128x2 payload should split into exactly 40 chunks of 1024 bytes."""
    image_data = bytes(range(256)) * 160  # 40960 bytes exactly
    chunks = chunk_image_data(image_data)
    assert len(chunks) == 40
    assert all(len(chunk) == CHUNK_SIZE for _, chunk in chunks)
    assert chunks[0][0] == 0
    assert chunks[1][0] == CHUNK_SIZE
    assert chunks[-1][0] == CHUNK_SIZE * 39


def test_build_write_frames_have_expected_len_and_offsets() -> None:
    """CMD_WRITE frames should carry 0x0400 payload length for full chunks."""
    image_data = bytes(range(256)) * 160  # 40960 bytes
    frames = build_write_frames(image_data)
    assert len(frames) == 40

    first_offset, first_chunk, first_frame = frames[0]
    assert first_offset == 0
    assert len(first_chunk) == CHUNK_SIZE
    # Frame format: A5 | cmd | addr_hi | addr_lo | len_hi | len_lo | payload | crc_hi | crc_lo
    assert first_frame[0] == 0xA5
    assert first_frame[1] == 0x57
    assert first_frame[4] == 0x04
    assert first_frame[5] == 0x00


def test_convert_image_to_rgb565_golden_vector_first_8_bytes(tmp_path) -> None:
    """Golden vector for known 2x2 RGB values (RGB565 little-endian)."""
    img = Image.new("RGB", (2, 2))
    img.putdata(
        [
            (255, 0, 0),   # red
            (0, 255, 0),   # green
            (0, 0, 255),   # blue
            (255, 255, 255),  # white
        ]
    )
    path = tmp_path / "tiny.png"
    img.save(path)

    out = convert_image_to_rgb565(str(path), size=(2, 2))

    # RGB565 little-endian:
    # red   -> 0xF800 -> 00 f8
    # green -> 0x07E0 -> e0 07
    # blue  -> 0x001F -> 1f 00
    # white -> 0xFFFF -> ff ff
    assert out[:8] == bytes([0x00, 0xF8, 0xE0, 0x07, 0x1F, 0x00, 0xFF, 0xFF])


def test_convert_image_to_rgb565_supports_bgr_order(tmp_path) -> None:
    """BGR565 remains available via explicit pixel_order override."""
    img = Image.new("RGB", (1, 1), color=(255, 0, 0))  # red
    path = tmp_path / "one.png"
    img.save(path)

    out = convert_image_to_rgb565(str(path), size=(1, 1), pixel_order="bgr")

    # red in BGR565 -> 0x001F -> 1f 00
    assert out == bytes([0x1F, 0x00])
