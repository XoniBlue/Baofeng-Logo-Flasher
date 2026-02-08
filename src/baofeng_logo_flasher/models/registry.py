"""
Model registry for Baofeng radios.

Provides a single source of truth for:
- Model configurations (protocol parameters, magic bytes, baud rates)
- Logo regions (size, format, address)
- Identification matchers (firmware version patterns)
- Capabilities (what operations are supported and why)

Usage:
    from baofeng_logo_flasher.models import (
        list_models, get_model, detect_model, get_capabilities
    )

    # List all known models
    models = list_models()

    # Get config for a specific model
    config = get_model("UV-5RM")

    # Detect model from identification bytes
    config = detect_model(ident_bytes, version_bytes)

    # Get capabilities report
    caps = get_capabilities("UV-5RM")
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional, Tuple


class Protocol(Enum):
    """Communication protocol type."""
    UV5R = "uv5r"       # 7-byte magic, 9600 baud
    UV17PRO = "uv17pro" # 16-byte magic, 115200 baud


class Capability(Enum):
    """Supported operation capability flags."""
    READ_CLONE = auto()         # Can read full clone image
    WRITE_CLONE = auto()        # Can write full clone image
    READ_LOGO = auto()          # Can read boot logo via clone protocol
    WRITE_LOGO = auto()         # Can write boot logo via clone protocol
    FLASH_LOGO = auto()         # Can flash logo to external SPI flash
    IDENTIFY = auto()           # Can identify radio model
    DETECT_FIRMWARE = auto()    # Can detect firmware version


class SafetyLevel(Enum):
    """Safety level for operations."""
    SAFE = "safe"           # No risk, read-only or reversible
    MODERATE = "moderate"   # Low risk, can be undone with backup
    RISKY = "risky"         # High risk, may brick device


@dataclass(frozen=True)
class LogoRegion:
    """Definition of a logo storage region."""
    start_addr: int
    length: int
    block_size: int = 64
    width: int = 160
    height: int = 128
    color_mode: str = "RGB"
    encrypt: bool = False
    encryption_key: bytes = b"\xAB\xCD\xEF"

    @property
    def dimensions(self) -> Tuple[int, int]:
        """Return (width, height) tuple."""
        return (self.width, self.height)

    @property
    def end_addr(self) -> int:
        """Return end address (exclusive)."""
        return self.start_addr + self.length


@dataclass(frozen=True)
class CapabilityInfo:
    """Information about a capability and its status for a model."""
    capability: Capability
    supported: bool
    reason: str
    safety: SafetyLevel = SafetyLevel.SAFE


@dataclass
class ModelCapabilities:
    """Complete capabilities report for a model."""
    model_name: str
    capabilities: List[CapabilityInfo]
    discovered_regions: List[LogoRegion]
    notes: List[str]

    def to_dict(self) -> Dict:
        """Convert to JSON-serializable dict."""
        return {
            "model": self.model_name,
            "capabilities": [
                {
                    "name": c.capability.name,
                    "supported": c.supported,
                    "reason": c.reason,
                    "safety": c.safety.value,
                }
                for c in self.capabilities
            ],
            "discovered_regions": [
                {
                    "start_addr": f"0x{r.start_addr:04X}",
                    "length": r.length,
                    "dimensions": f"{r.width}x{r.height}",
                    "color_mode": r.color_mode,
                    "encrypted": r.encrypt,
                }
                for r in self.discovered_regions
            ],
            "notes": self.notes,
        }


@dataclass
class ModelConfig:
    """
    Unified configuration for a radio model.

    Consolidates protocol parameters, logo regions, and identification info.
    """
    # Basic identification
    name: str
    vendor: str = "Baofeng"
    variant: Optional[str] = None

    # Protocol configuration
    protocol: Protocol = Protocol.UV5R
    baud_rate: int = 9600
    timeout: float = 3.0

    # Magic bytes for handshake
    magic_bytes: bytes = field(default=b"")

    # Additional post-ident magics (for UV17Pro protocol)
    post_ident_magics: List[Tuple[bytes, int]] = field(default_factory=list)
    fingerprint: bytes = b"\x06"

    # Identification matchers (patterns found in firmware version)
    ident_matchers: List[bytes] = field(default_factory=list)

    # Logo configuration
    logo_regions: List[LogoRegion] = field(default_factory=list)
    supported_formats: List[str] = field(default_factory=lambda: ["RGB"])

    # Clone memory info
    mem_size: int = 0x1808
    has_aux_block: bool = True

    # Notes and warnings
    notes: List[str] = field(default_factory=list)


# ============================================================================
# MODEL REGISTRY - All known models
# ============================================================================

_MODEL_REGISTRY: Dict[str, ModelConfig] = {}


def _register_model(config: ModelConfig) -> None:
    """Register a model configuration."""
    _MODEL_REGISTRY[config.name] = config


def _init_registry() -> None:
    """Initialize the model registry with known models."""

    # UV-5RM (A5 Logo Protocol)
    # Uses dedicated logo upload protocol at 115200 baud
    # Protocol: PROGRAMBFNORMALU handshake, 'D' mode, A5-framed commands
    _register_model(ModelConfig(
        name="UV-5RM",
        vendor="Baofeng",
        protocol=Protocol.UV17PRO,
        baud_rate=115200,
        timeout=2.0,
        magic_bytes=b"PROGRAMBFNORMALU",
        post_ident_magics=[],  # Not needed for logo upload - uses 'D' mode
        fingerprint=b"\x06",
        ident_matchers=[],
        logo_regions=[
            LogoRegion(
                start_addr=0x0000,  # Logo protocol uses its own addressing
                length=160 * 128 * 2,  # RGB565 = 2 bytes per pixel
                width=160,
                height=128,
                color_mode="RGB565",
                encrypt=False,  # A5 protocol handles its own framing
            ),
        ],
        supported_formats=["RGB565"],
        notes=[
            "Uses A5 logo protocol (T6UV CPS compatible)",
            "160x128 RGB565 display",
            "Logo uploaded via 'D' mode after handshake",
            "Data sent in 1024-byte chunks with CRC16-XMODEM checksum",
        ],
    ))

    # UV-17Pro (A5 Logo Protocol - same as UV-5RM)
    _register_model(ModelConfig(
        name="UV-17Pro",
        vendor="Baofeng",
        protocol=Protocol.UV17PRO,
        baud_rate=115200,
        timeout=2.0,
        magic_bytes=b"PROGRAMBFNORMALU",
        post_ident_magics=[],
        fingerprint=b"\x06",
        ident_matchers=[],
        logo_regions=[
            LogoRegion(
                start_addr=0x0000,
                length=160 * 128 * 2,
                width=160,
                height=128,
                color_mode="RGB565",
                encrypt=False,
            ),
        ],
        supported_formats=["RGB565"],
        notes=[
            "Uses A5 logo protocol (T6UV CPS compatible)",
            "160x128 RGB565 display",
            "Same protocol as UV-5RM",
        ],
    ))

    # UV-17R (A5 Logo Protocol - same as UV-5RM)
    _register_model(ModelConfig(
        name="UV-17R",
        vendor="Baofeng",
        protocol=Protocol.UV17PRO,
        baud_rate=115200,
        timeout=2.0,
        magic_bytes=b"PROGRAMBFNORMALU",
        post_ident_magics=[],
        fingerprint=b"\x06",
        ident_matchers=[],
        logo_regions=[
            LogoRegion(
                start_addr=0x0000,
                length=160 * 128 * 2,
                width=160,
                height=128,
                color_mode="RGB565",
                encrypt=False,
            ),
        ],
        supported_formats=["RGB565"],
        notes=[
            "Uses A5 logo protocol (T6UV CPS compatible)",
            "160x128 RGB565 display",
            "Same protocol as UV-5RM",
        ],
    ))

    # DM-32UV (UV5R protocol - legacy)
    _register_model(ModelConfig(
        name="DM-32UV",
        vendor="Baofeng",
        protocol=Protocol.UV5R,
        baud_rate=9600,
        timeout=3.0,
        magic_bytes=b"\x50\xBB\xFF\x20\x12\x07\x25",
        ident_matchers=[b"BFS", b"BFB"],
        logo_regions=[
            LogoRegion(
                start_addr=0x2000,
                length=240 * 320 * 3,
                width=240,
                height=320,
                color_mode="RGB",
                encrypt=False,
            ),
        ],
        supported_formats=["RGB"],
        notes=[
            "Uses standard UV5R protocol",
            "Larger display than UV-5R series",
        ],
    ))

    # UV-5RH Pro (clone-based, logo region unknown)
    _register_model(ModelConfig(
        name="UV-5RH Pro",
        vendor="Baofeng",
        protocol=Protocol.UV17PRO,
        baud_rate=115200,
        magic_bytes=b"PROGRAMBFNORMALU",
        ident_matchers=[],
        logo_regions=[],  # Requires discovery
        notes=[
            "Logo region not yet mapped",
            "Use scan-bitmaps command to discover logo location",
        ],
    ))

    # UV-17R
    _register_model(ModelConfig(
        name="UV-17R",
        vendor="Baofeng",
        protocol=Protocol.UV17PRO,
        baud_rate=115200,
        magic_bytes=b"PROGRAMBFNORMALU",
        ident_matchers=[],
        logo_regions=[],
        notes=["Logo region not yet mapped"],
    ))

    # UV-17R Pro
    _register_model(ModelConfig(
        name="UV-17R Pro",
        vendor="Baofeng",
        protocol=Protocol.UV17PRO,
        baud_rate=115200,
        magic_bytes=b"PROGRAMBFNORMALU",
        ident_matchers=[],
        logo_regions=[],
        notes=["Logo region not yet mapped"],
    ))

    # UV-5R (BFB291+ firmware)
    _register_model(ModelConfig(
        name="UV-5R",
        vendor="Baofeng",
        protocol=Protocol.UV5R,
        baud_rate=9600,
        magic_bytes=b"\x50\xBB\xFF\x20\x12\x07\x25",
        ident_matchers=[b"BFS", b"BFB", b"N5R-2", b"N5R2", b"N5RV", b"BTS", b"D5R2", b"B5R2"],
        logo_regions=[],  # Logo in MCU flash, not accessible via clone
        mem_size=0x1808,
        notes=[
            "Original UV-5R series",
            "Boot logo in MCU internal flash",
            "Not accessible via clone protocol",
        ],
    ))

    # UV-5R Original (pre-BFB291)
    _register_model(ModelConfig(
        name="UV-5R-ORIG",
        vendor="Baofeng",
        protocol=Protocol.UV5R,
        baud_rate=9600,
        magic_bytes=b"\x50\xBB\xFF\x01\x25\x98\x4D",
        ident_matchers=[b"BFS", b"BFB"],
        logo_regions=[],
        notes=["Original firmware, pre-BFB291"],
    ))

    # UV-82
    _register_model(ModelConfig(
        name="UV-82",
        vendor="Baofeng",
        protocol=Protocol.UV5R,
        baud_rate=9600,
        magic_bytes=b"\x50\xBB\xFF\x20\x13\x01\x05",
        ident_matchers=[b"US2S2", b"B82S", b"BF82", b"N82-2", b"N822"],
        logo_regions=[],
        notes=["UV-82 series, VHF/UHF dual band"],
    ))

    # UV-6
    _register_model(ModelConfig(
        name="UV-6",
        vendor="Baofeng",
        protocol=Protocol.UV5R,
        baud_rate=9600,
        magic_bytes=b"\x50\xBB\xFF\x20\x12\x08\x23",
        ident_matchers=[b"BF1", b"UV6"],
        logo_regions=[],
        notes=["UV-6 series"],
    ))

    # F-11
    _register_model(ModelConfig(
        name="F-11",
        vendor="Baofeng",
        protocol=Protocol.UV5R,
        baud_rate=9600,
        magic_bytes=b"\x50\xBB\xFF\x13\xA1\x11\xDD",
        ident_matchers=[b"USA"],
        logo_regions=[],
        notes=["Compact form factor"],
    ))

    # A-58
    _register_model(ModelConfig(
        name="A-58",
        vendor="Baofeng",
        protocol=Protocol.UV5R,
        baud_rate=9600,
        magic_bytes=b"\x50\xBB\xFF\x20\x14\x04\x13",
        ident_matchers=[],
        logo_regions=[],
        notes=["A-58 radio"],
    ))

    # UV-5G
    _register_model(ModelConfig(
        name="UV-5G",
        vendor="Baofeng",
        protocol=Protocol.UV5R,
        baud_rate=9600,
        magic_bytes=b"\x50\xBB\xFF\x20\x12\x06\x25",
        ident_matchers=[],
        logo_regions=[],
        notes=["UV-5G variant"],
    ))

    # F-8HP
    _register_model(ModelConfig(
        name="F-8HP",
        vendor="Baofeng",
        protocol=Protocol.UV5R,
        baud_rate=9600,
        magic_bytes=b"\x50\xBB\xFF\x20\x12\x07\x25",
        ident_matchers=[b"BFP3V3 F", b"N5R-3", b"N5R3", b"F5R3", b"BFT", b"N5RV"],
        logo_regions=[],
        notes=["Higher power variant of UV-5R"],
    ))

    # UV-82HP
    _register_model(ModelConfig(
        name="UV-82HP",
        vendor="Baofeng",
        protocol=Protocol.UV5R,
        baud_rate=9600,
        magic_bytes=b"\x50\xBB\xFF\x20\x13\x01\x05",
        ident_matchers=[b"N82-3", b"N823", b"N5R2"],
        logo_regions=[],
        notes=["Higher power UV-82 variant"],
    ))

    # Radioddity 82X3
    _register_model(ModelConfig(
        name="82X3",
        vendor="Radioddity",
        protocol=Protocol.UV5R,
        baud_rate=9600,
        magic_bytes=b"\x50\xBB\xFF\x20\x13\x01\x05",
        ident_matchers=[b"HN5RV01"],
        logo_regions=[],
        notes=["Tri-band variant"],
    ))


# Initialize registry on module load
_init_registry()


# ============================================================================
# PUBLIC API
# ============================================================================

def list_models() -> List[str]:
    """
    List all registered model names.

    Returns:
        Sorted list of model names.
    """
    return sorted(_MODEL_REGISTRY.keys())


def get_model(name: str) -> Optional[ModelConfig]:
    """
    Get configuration for a specific model.

    Args:
        name: Model name (case-sensitive)

    Returns:
        ModelConfig or None if not found.
    """
    return _MODEL_REGISTRY.get(name)


def detect_model(
    ident_bytes: Optional[bytes] = None,
    version_bytes: Optional[bytes] = None,
    magic_used: Optional[bytes] = None,
) -> Optional[ModelConfig]:
    """
    Detect model from identification bytes.

    Matches firmware version patterns against registered models.

    Args:
        ident_bytes: 8-byte radio identification (from handshake)
        version_bytes: Firmware version string (from memory read)
        magic_used: Magic bytes that successfully identified the radio

    Returns:
        Best matching ModelConfig, or None if no match.
    """
    if version_bytes:
        # Try to match firmware version patterns
        for config in _MODEL_REGISTRY.values():
            for matcher in config.ident_matchers:
                if matcher in version_bytes:
                    return config

    # Try to match by magic bytes used
    if magic_used:
        for config in _MODEL_REGISTRY.values():
            if config.magic_bytes == magic_used:
                return config

    return None


def get_capabilities(
    model_name: str,
    discovered_regions: Optional[List[LogoRegion]] = None,
) -> ModelCapabilities:
    """
    Get capabilities report for a model.

    Args:
        model_name: Model name to check
        discovered_regions: Optional list of discovered logo regions
            (from bitmap scanning or other discovery)

    Returns:
        ModelCapabilities report with supported operations and reasons.
    """
    config = get_model(model_name)

    if config is None:
        return ModelCapabilities(
            model_name=model_name,
            capabilities=[
                CapabilityInfo(
                    Capability.IDENTIFY,
                    False,
                    "Unknown model - not in registry",
                    SafetyLevel.SAFE,
                ),
            ],
            discovered_regions=discovered_regions or [],
            notes=["Model not found in registry. Use list-models to see known models."],
        )

    caps = []
    regions = list(config.logo_regions) + (discovered_regions or [])

    # IDENTIFY capability
    caps.append(CapabilityInfo(
        Capability.IDENTIFY,
        True,
        f"Supported via {config.protocol.value} protocol",
        SafetyLevel.SAFE,
    ))

    # DETECT_FIRMWARE capability
    caps.append(CapabilityInfo(
        Capability.DETECT_FIRMWARE,
        True,
        "Firmware version readable from memory",
        SafetyLevel.SAFE,
    ))

    # READ_CLONE capability
    caps.append(CapabilityInfo(
        Capability.READ_CLONE,
        True,
        f"Clone download via {config.protocol.value} protocol",
        SafetyLevel.SAFE,
    ))

    # WRITE_CLONE capability
    caps.append(CapabilityInfo(
        Capability.WRITE_CLONE,
        True,
        f"Clone upload via {config.protocol.value} protocol",
        SafetyLevel.MODERATE,
    ))

    # READ_LOGO capability
    has_region = len(regions) > 0
    if has_region:
        caps.append(CapabilityInfo(
            Capability.READ_LOGO,
            True,
            f"Logo region mapped at 0x{regions[0].start_addr:04X}",
            SafetyLevel.SAFE,
        ))
    else:
        caps.append(CapabilityInfo(
            Capability.READ_LOGO,
            False,
            "Logo region not mapped - use scan-bitmaps to discover",
            SafetyLevel.SAFE,
        ))

    # WRITE_LOGO capability
    if has_region:
        # Check if logo is in clone-accessible memory
        is_spi_flash = any("SPI flash" in n for n in config.notes)
        if is_spi_flash:
            caps.append(CapabilityInfo(
                Capability.WRITE_LOGO,
                False,
                "Logo on external SPI flash - not accessible via clone protocol",
                SafetyLevel.RISKY,
            ))
        else:
            caps.append(CapabilityInfo(
                Capability.WRITE_LOGO,
                True,
                f"Logo region writable at 0x{regions[0].start_addr:04X}",
                SafetyLevel.MODERATE,
            ))
    else:
        caps.append(CapabilityInfo(
            Capability.WRITE_LOGO,
            False,
            "Logo region not mapped",
            SafetyLevel.SAFE,
        ))

    # FLASH_LOGO capability (direct SPI flash access)
    is_uv17pro = config.protocol == Protocol.UV17PRO
    if is_uv17pro and has_region:
        caps.append(CapabilityInfo(
            Capability.FLASH_LOGO,
            True,
            "Experimental - may require firmware-level access",
            SafetyLevel.RISKY,
        ))
    else:
        caps.append(CapabilityInfo(
            Capability.FLASH_LOGO,
            False,
            "Not available for this model/protocol",
            SafetyLevel.SAFE,
        ))

    return ModelCapabilities(
        model_name=model_name,
        capabilities=caps,
        discovered_regions=regions,
        notes=config.notes,
    )


def get_magic_bytes_for_protocol(protocol: Protocol) -> List[bytes]:
    """
    Get all known magic byte sequences for a protocol type.

    Args:
        protocol: Protocol type to get magic bytes for

    Returns:
        List of magic byte sequences.
    """
    magics = []
    for config in _MODEL_REGISTRY.values():
        if config.protocol == protocol and config.magic_bytes:
            if config.magic_bytes not in magics:
                magics.append(config.magic_bytes)
    return magics


def get_models_by_protocol(protocol: Protocol) -> List[ModelConfig]:
    """
    Get all models using a specific protocol.

    Args:
        protocol: Protocol type to filter by

    Returns:
        List of ModelConfig instances.
    """
    return [
        config for config in _MODEL_REGISTRY.values()
        if config.protocol == protocol
    ]


def get_serial_flash_config(model_name: str) -> Optional[Dict]:
    """
    Get configuration in legacy SERIAL_FLASH_CONFIGS format.

    Provides backward compatibility with existing code that expects
    the dictionary format used by boot_logo.SERIAL_FLASH_CONFIGS.

    Args:
        model_name: Model name to get config for

    Returns:
        Dict with keys: size, color_mode, encrypt, start_addr, magic,
        block_size, key, baudrate, timeout, post_ident_magics, fingerprint.
        Returns None if model not found or has no logo regions.
    """
    config = get_model(model_name)
    if config is None:
        return None

    # Need at least one logo region to produce a flash config
    if not config.logo_regions:
        # Return basic protocol config without logo specifics
        return {
            "size": (160, 128),  # Default
            "color_mode": "RGB",
            "encrypt": False,
            "start_addr": 0x0000,
            "magic": config.magic_bytes,
            "block_size": 64,
            "key": b"\xAB\xCD\xEF",
            "baudrate": config.baud_rate,
            "timeout": config.timeout,
            "post_ident_magics": config.post_ident_magics,
            "fingerprint": config.fingerprint,
        }

    region = config.logo_regions[0]
    return {
        "size": (region.width, region.height),
        "color_mode": region.color_mode,
        "encrypt": region.encrypt,
        "start_addr": region.start_addr,
        "magic": config.magic_bytes,
        "block_size": region.block_size,
        "key": region.encryption_key,
        "baudrate": config.baud_rate,
        "timeout": config.timeout,
        "post_ident_magics": config.post_ident_magics,
        "fingerprint": config.fingerprint,
    }


def get_all_serial_flash_configs() -> Dict[str, Dict]:
    """
    Get all models as SERIAL_FLASH_CONFIGS format dict.

    Returns:
        Dict mapping model names to their flash configs.
    """
    result = {}
    for model_name in list_models():
        config = get_serial_flash_config(model_name)
        if config:
            result[model_name] = config
    return result
