"""Radio protocol layer - CHIRP integration and logo protocols."""

from .uv5rm_transport import (
    UV5RMTransport,
    RadioTransportError,
    RadioNoContact,
    RadioBlockError,
)
from .uv5rm_protocol import UV5RMProtocol, RadioModel
from .logo_protocol import (
    LogoUploader,
    LogoProtocolError,
    upload_logo as logo_upload,
    convert_image_to_rgb565,
    IMAGE_WIDTH,
    IMAGE_HEIGHT,
    IMAGE_BYTES,
    CHUNK_SIZE,
)
from .dm32uv_picture_protocol import (
    DM32UVPictureUploader,
    DM32UVProtocolError,
    build_dm32uv_bin_from_image,
    parse_dm32uv_bin,
    DM32UVBinHeader,
)

__all__ = [
    # Transport
    "UV5RMTransport",
    "UV5RMProtocol",
    "RadioModel",
    "RadioTransportError",
    "RadioNoContact",
    "RadioBlockError",
    # Logo protocol
    "LogoUploader",
    "LogoProtocolError",
    "logo_upload",
    "convert_image_to_rgb565",
    "IMAGE_WIDTH",
    "IMAGE_HEIGHT",
    "IMAGE_BYTES",
    "CHUNK_SIZE",
    # DM32UV picture protocol
    "DM32UVPictureUploader",
    "DM32UVProtocolError",
    "build_dm32uv_bin_from_image",
    "parse_dm32uv_bin",
    "DM32UVBinHeader",
]
