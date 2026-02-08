"""
Feature registry for Baofeng Logo Flasher.

Provides a centralized registry of available operations/tools with metadata.
Used to:
- Render unified sidebar navigation in Streamlit
- Generate consistent CLI help text
- Track which features support UI vs CLI
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Callable, Dict, Any


class RiskLevel(Enum):
    """Risk level for operations."""
    NONE = "none"  # Read-only, no risk
    LOW = "low"  # Minimal risk, easily recoverable
    MEDIUM = "medium"  # Some risk, backup recommended
    HIGH = "high"  # High risk, could brick device


class FeatureCategory(Enum):
    """Feature categories for grouping."""
    FLASH = "flash"  # Logo flashing operations
    READ = "read"  # Read/download operations
    TOOLS = "tools"  # Utility tools
    VERIFY = "verify"  # Verification operations
    CONFIG = "config"  # Configuration/settings


@dataclass
class Feature:
    """
    Definition of a feature/operation with metadata.

    Attributes:
        id: Unique identifier (used in CLI command names)
        name: Human-readable name
        description: Short description for help text
        category: Feature category for grouping
        supports_ui: Whether available in Streamlit UI
        supports_cli: Whether available in CLI
        risk_level: Risk level for safety warnings
        cli_command: CLI command name (if different from id)
        ui_tab: Which UI tab this appears in
        icon: Emoji icon for display
        requires_write: Whether this operation writes to device
        requires_connection: Whether this needs radio connection
        entrypoint: Reference to the core function (optional)
    """
    id: str
    name: str
    description: str
    category: FeatureCategory
    supports_ui: bool = True
    supports_cli: bool = True
    risk_level: RiskLevel = RiskLevel.NONE
    cli_command: Optional[str] = None
    ui_tab: Optional[str] = None
    icon: str = "🔧"
    requires_write: bool = False
    requires_connection: bool = False
    entrypoint: Optional[Callable] = None
    tags: List[str] = field(default_factory=list)

    def __post_init__(self):
        if self.cli_command is None:
            self.cli_command = self.id.replace("_", "-")

    @property
    def is_dangerous(self) -> bool:
        """Check if this is a high-risk operation."""
        return self.risk_level == RiskLevel.HIGH

    @property
    def needs_confirmation(self) -> bool:
        """Check if this operation needs write confirmation."""
        return self.requires_write or self.risk_level in (RiskLevel.MEDIUM, RiskLevel.HIGH)


# Global feature registry
_FEATURES: Dict[str, Feature] = {}


def register_feature(feature: Feature) -> Feature:
    """Register a feature in the global registry."""
    _FEATURES[feature.id] = feature
    return feature


def get_feature(feature_id: str) -> Optional[Feature]:
    """Get a feature by ID."""
    return _FEATURES.get(feature_id)


def get_all_features() -> List[Feature]:
    """Get all registered features."""
    return list(_FEATURES.values())


def get_features_by_category(category: FeatureCategory) -> List[Feature]:
    """Get all features in a category."""
    return [f for f in _FEATURES.values() if f.category == category]


def get_ui_features() -> List[Feature]:
    """Get all features available in the UI."""
    return [f for f in _FEATURES.values() if f.supports_ui]


def get_cli_features() -> List[Feature]:
    """Get all features available in the CLI."""
    return [f for f in _FEATURES.values() if f.supports_cli]


def get_features_by_risk(risk_level: RiskLevel) -> List[Feature]:
    """Get all features at a specific risk level."""
    return [f for f in _FEATURES.values() if f.risk_level == risk_level]


# =============================================================================
# Register all features
# =============================================================================

# Flash operations
register_feature(Feature(
    id="flash_logo",
    name="Flash Logo",
    description="Complete workflow: download clone → backup → patch logo → upload → verify",
    category=FeatureCategory.FLASH,
    risk_level=RiskLevel.HIGH,
    icon="⚡",
    ui_tab="Boot Logo Flasher",
    requires_write=True,
    requires_connection=True,
    tags=["write", "logo", "serial"],
))

register_feature(Feature(
    id="flash_logo_serial",
    name="Direct Serial Flash",
    description="Flash logo directly via serial protocol (UV-5RM style)",
    category=FeatureCategory.FLASH,
    risk_level=RiskLevel.HIGH,
    icon="📡",
    ui_tab="Boot Logo Flasher",
    requires_write=True,
    requires_connection=True,
    tags=["write", "logo", "serial", "direct"],
))

register_feature(Feature(
    id="upload_logo",
    name="Upload Logo",
    description="Upload a boot logo to the radio",
    category=FeatureCategory.FLASH,
    risk_level=RiskLevel.HIGH,
    icon="⬆️",
    requires_write=True,
    requires_connection=True,
    tags=["write", "logo", "upload"],
))

# Read operations
register_feature(Feature(
    id="read_clone",
    name="Read Clone",
    description="Download clone image from radio",
    category=FeatureCategory.READ,
    risk_level=RiskLevel.NONE,
    icon="⬇️",
    ui_tab="Tools & Inspect",
    requires_connection=True,
    tags=["read", "clone", "backup"],
))

register_feature(Feature(
    id="download_logo",
    name="Download Logo",
    description="Download boot logo from the radio",
    category=FeatureCategory.READ,
    risk_level=RiskLevel.NONE,
    icon="🖼️",
    requires_connection=True,
    tags=["read", "logo", "backup"],
))

register_feature(Feature(
    id="read_radio_id",
    name="Read Radio ID",
    description="Connect and read radio identification",
    category=FeatureCategory.READ,
    risk_level=RiskLevel.NONE,
    icon="📋",
    requires_connection=True,
    tags=["read", "identify"],
))

# Tools
register_feature(Feature(
    id="patch_logo",
    name="Patch Logo (Offline)",
    description="Patch logo into clone image file without radio connection",
    category=FeatureCategory.TOOLS,
    risk_level=RiskLevel.LOW,
    icon="🖌️",
    ui_tab="Verify & Patch",
    tags=["patch", "offline", "logo"],
))

register_feature(Feature(
    id="scan_logo",
    name="Scan for Logos",
    description="Scan clone image for candidate logo bitmap regions",
    category=FeatureCategory.TOOLS,
    risk_level=RiskLevel.NONE,
    icon="🔍",
    ui_tab="Tools & Inspect",
    tags=["scan", "discover", "logo"],
))

register_feature(Feature(
    id="inspect_img",
    name="Inspect Image",
    description="Inspect CHIRP clone image for structure and safety",
    category=FeatureCategory.TOOLS,
    risk_level=RiskLevel.NONE,
    icon="🔎",
    ui_tab="Tools & Inspect",
    tags=["inspect", "analyze"],
))

register_feature(Feature(
    id="convert_image",
    name="Convert Image",
    description="Convert any image to radio-compatible BMP format",
    category=FeatureCategory.TOOLS,
    risk_level=RiskLevel.NONE,
    icon="🖼️",
    ui_tab="Tools & Inspect",
    tags=["convert", "image", "bmp"],
))

register_feature(Feature(
    id="list_ports",
    name="List Ports",
    description="List available serial ports",
    category=FeatureCategory.TOOLS,
    risk_level=RiskLevel.NONE,
    icon="🔌",
    cli_command="ports",
    supports_ui=False,
    tags=["ports", "serial"],
))

register_feature(Feature(
    id="list_models",
    name="List Models",
    description="List supported radio models and configurations",
    category=FeatureCategory.TOOLS,
    risk_level=RiskLevel.NONE,
    icon="📻",
    supports_ui=False,
    tags=["models", "list"],
))

# Verification
register_feature(Feature(
    id="verify_image",
    name="Verify Image",
    description="Verify clone image against protocol assumptions",
    category=FeatureCategory.VERIFY,
    risk_level=RiskLevel.NONE,
    icon="✓",
    ui_tab="Verify & Patch",
    tags=["verify", "safety"],
))

register_feature(Feature(
    id="detect",
    name="Detect Radio",
    description="Identify radio model and firmware",
    category=FeatureCategory.VERIFY,
    risk_level=RiskLevel.NONE,
    icon="📡",
    requires_connection=True,
    tags=["detect", "identify"],
))


# =============================================================================
# Helper functions for UI/CLI integration
# =============================================================================

def get_sidebar_navigation() -> Dict[str, List[Feature]]:
    """
    Get features organized for sidebar navigation.

    Returns dict with category names as keys and feature lists as values.
    """
    nav = {}
    for category in FeatureCategory:
        features = [f for f in get_ui_features() if f.category == category]
        if features:
            # Use category value with proper capitalization for display
            display_name = category.value.replace("_", " ").title()
            nav[display_name] = features
    return nav


def get_cli_help_groups() -> Dict[str, List[Feature]]:
    """
    Get features organized for CLI help groups.

    Returns dict with group names and feature lists.
    """
    groups = {
        "Flash Operations": [],
        "Read Operations": [],
        "Tools": [],
        "Verification": [],
    }

    category_to_group = {
        FeatureCategory.FLASH: "Flash Operations",
        FeatureCategory.READ: "Read Operations",
        FeatureCategory.TOOLS: "Tools",
        FeatureCategory.VERIFY: "Verification",
        FeatureCategory.CONFIG: "Configuration",
    }

    for feature in get_cli_features():
        group = category_to_group.get(feature.category, "Other")
        if group not in groups:
            groups[group] = []
        groups[group].append(feature)

    # Remove empty groups
    return {k: v for k, v in groups.items() if v}


def format_feature_for_cli_help(feature: Feature) -> str:
    """Format a feature for CLI help text."""
    risk_icons = {
        RiskLevel.NONE: "",
        RiskLevel.LOW: "[low risk]",
        RiskLevel.MEDIUM: "[⚠️ medium risk]",
        RiskLevel.HIGH: "[🚨 high risk]",
    }
    risk = risk_icons.get(feature.risk_level, "")
    return f"  {feature.cli_command:<20} {feature.description} {risk}"
