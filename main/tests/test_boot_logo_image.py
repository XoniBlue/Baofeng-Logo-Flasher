import io
from PIL import Image

from baofeng_logo_flasher.bmp_utils import validate_bmp_bytes, convert_image_to_bmp_bytes
from baofeng_logo_flasher.boot_logo import BOOT_LOGO_SIZE


def test_validate_bmp_bytes_roundtrip() -> None:
    img = Image.new("RGB", BOOT_LOGO_SIZE, "red")
    buffer = io.BytesIO()
    img.save(buffer, format="BMP")
    data = buffer.getvalue()

    info = validate_bmp_bytes(data, BOOT_LOGO_SIZE)
    assert info.width == BOOT_LOGO_SIZE[0]
    assert info.height == BOOT_LOGO_SIZE[1]
    assert info.bits_per_pixel == 24


def test_convert_image_to_bmp_bytes(tmp_path) -> None:
    src = tmp_path / "source.png"
    Image.new("RGB", (80, 64), "blue").save(src)

    data = convert_image_to_bmp_bytes(str(src), BOOT_LOGO_SIZE)
    info = validate_bmp_bytes(data, BOOT_LOGO_SIZE)
    assert info.width == BOOT_LOGO_SIZE[0]
    assert info.height == BOOT_LOGO_SIZE[1]
