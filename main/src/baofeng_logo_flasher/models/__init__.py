"""
Model registry for Baofeng radios.

Provides a unified layer for model discovery, configuration, and capabilities.
"""

from .registry import (
    ModelConfig,
    LogoRegion,
    Capability,
    ModelCapabilities,
    Protocol,
    SafetyLevel,
    CapabilityInfo,
    list_models,
    get_model,
    detect_model,
    get_capabilities,
    get_magic_bytes_for_protocol,
    get_models_by_protocol,
    get_serial_flash_config,
    get_all_serial_flash_configs,
)

__all__ = [
    "ModelConfig",
    "LogoRegion",
    "Capability",
    "ModelCapabilities",
    "Protocol",
    "SafetyLevel",
    "CapabilityInfo",
    "list_models",
    "get_model",
    "detect_model",
    "get_capabilities",
    "get_magic_bytes_for_protocol",
    "get_models_by_protocol",
    "get_serial_flash_config",
    "get_all_serial_flash_configs",
]
