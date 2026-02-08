"""
Core module for Baofeng Logo Flasher.

This module provides the single source of truth for:
- Write gating / confirmation (safety.py)
- Offset and format parsing (parsing.py)
- Result objects (results.py)
- Unified read/verify/write workflows (actions.py)
- Standardized warnings/messages (messages.py)

Both CLI and Streamlit UI should call into this module rather than
implementing their own logic.
"""

from .safety import SafetyContext, require_write_permission, WritePermissionError
from .parsing import parse_offset, parse_bitmap_format
from .results import OperationResult
from .messages import (
    MessageLevel,
    WarningCode,
    WarningItem,
    warnings_from_strings,
    result_to_warnings,
    COMMON_WARNINGS,
)
from .actions import (
    prepare_logo_bytes,
    read_clone,
    verify_clone,
    write_logo,
    flash_logo,
    patch_logo_offline,
    flash_logo_serial,
)

__all__ = [
    # Safety
    "SafetyContext",
    "require_write_permission",
    "WritePermissionError",
    # Parsing
    "parse_offset",
    "parse_bitmap_format",
    # Results
    "OperationResult",
    # Messages
    "MessageLevel",
    "WarningCode",
    "WarningItem",
    "warnings_from_strings",
    "result_to_warnings",
    "COMMON_WARNINGS",
    # Actions
    "prepare_logo_bytes",
    "read_clone",
    "verify_clone",
    "write_logo",
    "flash_logo",
    "patch_logo_offline",
    "flash_logo_serial",
]
