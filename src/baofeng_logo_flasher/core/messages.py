"""
Standardized warning and message system for Baofeng Logo Flasher.

Provides structured warning items with stable codes that both CLI and
Streamlit can display consistently.
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Dict, Any


class MessageLevel(Enum):
    """Severity level for messages."""
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


# Standard warning codes for consistent messaging across CLI and UI
class WarningCode(Enum):
    """Stable warning codes for known conditions."""
    # Model/Device warnings
    W_MODEL_UNKNOWN = "W_MODEL_UNKNOWN"
    W_MODEL_UNSUPPORTED = "W_MODEL_UNSUPPORTED"
    W_DEVICE_NOT_FOUND = "W_DEVICE_NOT_FOUND"

    # Region/Memory warnings
    W_REGION_UNCONFIRMED = "W_REGION_UNCONFIRMED"
    W_REGION_READ_ONLY = "W_REGION_READ_ONLY"
    W_OFFSET_GUESSED = "W_OFFSET_GUESSED"

    # Safety warnings
    W_BACKUP_FAILED = "W_BACKUP_FAILED"
    W_VERIFY_MISMATCH = "W_VERIFY_MISMATCH"
    W_WRITE_DISABLED = "W_WRITE_DISABLED"
    W_CONFIRMATION_REQUIRED = "W_CONFIRMATION_REQUIRED"

    # Connection warnings
    W_SERIAL_TIMEOUT = "W_SERIAL_TIMEOUT"
    W_SERIAL_ERROR = "W_SERIAL_ERROR"
    W_HANDSHAKE_FAILED = "W_HANDSHAKE_FAILED"

    # Data warnings
    W_DATA_TRUNCATED = "W_DATA_TRUNCATED"
    W_DATA_PADDED = "W_DATA_PADDED"
    W_FORMAT_MISMATCH = "W_FORMAT_MISMATCH"
    W_SIZE_MISMATCH = "W_SIZE_MISMATCH"

    # Operation warnings
    W_SIMULATED = "W_SIMULATED"
    W_DRY_RUN = "W_DRY_RUN"
    W_PARTIAL_SUCCESS = "W_PARTIAL_SUCCESS"

    # Generic
    W_UNKNOWN = "W_UNKNOWN"


# Default remediation hints for each warning code
WARNING_REMEDIATIONS: Dict[WarningCode, str] = {
    WarningCode.W_MODEL_UNKNOWN:
        "Connect radio and ensure it's powered on. Try different baud rates.",
    WarningCode.W_MODEL_UNSUPPORTED:
        "Check supported models with 'list-models' command.",
    WarningCode.W_DEVICE_NOT_FOUND:
        "Check USB connection, try 'ports' command to list available ports.",
    WarningCode.W_REGION_UNCONFIRMED:
        "Use --offset to specify exact address, or run discovery mode.",
    WarningCode.W_REGION_READ_ONLY:
        "This memory region cannot be written. Boot logo may be in external flash.",
    WarningCode.W_OFFSET_GUESSED:
        "Offset was auto-detected. Verify with scan-logo before writing.",
    WarningCode.W_BACKUP_FAILED:
        "Ensure write permissions in backup directory. Do not proceed without backup.",
    WarningCode.W_VERIFY_MISMATCH:
        "Data read back does not match what was written. Check connection stability.",
    WarningCode.W_WRITE_DISABLED:
        "Add --write flag (CLI) or enable write mode (UI) to perform actual writes.",
    WarningCode.W_CONFIRMATION_REQUIRED:
        "Type 'WRITE' to confirm the operation.",
    WarningCode.W_SERIAL_TIMEOUT:
        "Check cable connection. Try lower baud rate or increase timeout.",
    WarningCode.W_SERIAL_ERROR:
        "Close other serial apps (CHIRP, Arduino IDE). Check USB driver.",
    WarningCode.W_HANDSHAKE_FAILED:
        "Radio may be in wrong mode. Try power cycling the radio.",
    WarningCode.W_DATA_TRUNCATED:
        "Data was cut off. Check file integrity and size requirements.",
    WarningCode.W_DATA_PADDED:
        "Data was padded to meet size requirements.",
    WarningCode.W_FORMAT_MISMATCH:
        "Image format does not match expected format. Try different --format option.",
    WarningCode.W_SIZE_MISMATCH:
        "Image dimensions don't match. Resize to exact required dimensions.",
    WarningCode.W_SIMULATED:
        "No actual write was performed. Remove simulation mode to write.",
    WarningCode.W_DRY_RUN:
        "Dry run complete. Add --write flag to perform actual operation.",
    WarningCode.W_PARTIAL_SUCCESS:
        "Some operations failed. Check individual errors below.",
    WarningCode.W_UNKNOWN:
        "Check logs for more details.",
}


@dataclass
class WarningItem:
    """
    Structured warning message with stable code.

    Attributes:
        level: Severity (INFO, WARN, ERROR)
        code: Stable warning code for programmatic handling
        title: Short, user-facing title
        detail: Longer explanation of the issue
        remediation: Suggested action to resolve the issue
    """
    level: MessageLevel
    code: WarningCode
    title: str
    detail: str = ""
    remediation: str = ""

    def __post_init__(self):
        """Set default remediation if not provided."""
        if not self.remediation and self.code in WARNING_REMEDIATIONS:
            self.remediation = WARNING_REMEDIATIONS[self.code]

    @classmethod
    def info(
        cls,
        code: WarningCode,
        title: str,
        detail: str = "",
        remediation: str = "",
    ) -> "WarningItem":
        """Create an INFO-level warning."""
        return cls(MessageLevel.INFO, code, title, detail, remediation)

    @classmethod
    def warn(
        cls,
        code: WarningCode,
        title: str,
        detail: str = "",
        remediation: str = "",
    ) -> "WarningItem":
        """Create a WARN-level warning."""
        return cls(MessageLevel.WARN, code, title, detail, remediation)

    @classmethod
    def error(
        cls,
        code: WarningCode,
        title: str,
        detail: str = "",
        remediation: str = "",
    ) -> "WarningItem":
        """Create an ERROR-level warning."""
        return cls(MessageLevel.ERROR, code, title, detail, remediation)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON/display."""
        return {
            "level": self.level.value,
            "code": self.code.value,
            "title": self.title,
            "detail": self.detail,
            "remediation": self.remediation,
        }

    def to_cli_string(self, verbose: bool = False) -> str:
        """Format for CLI output."""
        icons = {
            MessageLevel.INFO: "ℹ️ ",
            MessageLevel.WARN: "⚠️ ",
            MessageLevel.ERROR: "❌",
        }
        icon = icons.get(self.level, "")

        if verbose:
            lines = [f"{icon} [{self.code.value}] {self.title}"]
            if self.detail:
                lines.append(f"   {self.detail}")
            if self.remediation:
                lines.append(f"   → {self.remediation}")
            return "\n".join(lines)
        else:
            return f"{icon} {self.title}"


def warnings_from_strings(
    warning_strings: List[str],
    default_level: MessageLevel = MessageLevel.WARN,
) -> List[WarningItem]:
    """
    Convert plain warning strings to WarningItem list.

    Attempts to detect known patterns and assign appropriate codes.

    Args:
        warning_strings: List of plain warning message strings
        default_level: Default severity level

    Returns:
        List of WarningItem objects
    """
    items = []

    for msg in warning_strings:
        msg_lower = msg.lower()

        # Try to detect known patterns
        if "model" in msg_lower and ("unknown" in msg_lower or "not identified" in msg_lower):
            code = WarningCode.W_MODEL_UNKNOWN
        elif "simulation" in msg_lower or "simulated" in msg_lower:
            code = WarningCode.W_SIMULATED
        elif "backup" in msg_lower and "fail" in msg_lower:
            code = WarningCode.W_BACKUP_FAILED
        elif "verify" in msg_lower or "mismatch" in msg_lower:
            code = WarningCode.W_VERIFY_MISMATCH
        elif "timeout" in msg_lower:
            code = WarningCode.W_SERIAL_TIMEOUT
        elif "region" in msg_lower and "unknown" in msg_lower:
            code = WarningCode.W_REGION_UNCONFIRMED
        elif "read-only" in msg_lower or "0x52" in msg_lower:
            code = WarningCode.W_REGION_READ_ONLY
        else:
            code = WarningCode.W_UNKNOWN

        items.append(WarningItem(
            level=default_level,
            code=code,
            title=msg,
        ))

    return items


def result_to_warnings(result: "OperationResult") -> List[WarningItem]:
    """
    Convert Result object's warnings and errors to WarningItem list.

    Args:
        result: OperationResult from core operations

    Returns:
        List of WarningItem objects
    """
    # Import here to avoid circular imports
    from .results import OperationResult

    items = []

    # Convert warning strings
    items.extend(warnings_from_strings(result.warnings, MessageLevel.WARN))

    # Convert error strings
    for err in result.errors:
        err_lower = err.lower()

        if "timeout" in err_lower:
            code = WarningCode.W_SERIAL_TIMEOUT
        elif "model" in err_lower and "unknown" in err_lower:
            code = WarningCode.W_MODEL_UNKNOWN
        elif "permission" in err_lower or "write" in err_lower:
            code = WarningCode.W_WRITE_DISABLED
        else:
            code = WarningCode.W_UNKNOWN

        items.append(WarningItem.error(code, err))

    return items


# Pre-built common warnings for convenience
COMMON_WARNINGS = {
    "model_unknown": WarningItem.warn(
        WarningCode.W_MODEL_UNKNOWN,
        "Radio model could not be identified",
        "The radio did not respond with a recognized model identifier.",
    ),
    "simulation_mode": WarningItem.info(
        WarningCode.W_SIMULATED,
        "Simulation mode - no actual write performed",
        "This was a dry run. Enable write mode to perform the actual operation.",
    ),
    "write_disabled": WarningItem.warn(
        WarningCode.W_WRITE_DISABLED,
        "Write mode is disabled",
        "You are in read-only mode. Enable write mode to make changes.",
    ),
    "confirmation_required": WarningItem.warn(
        WarningCode.W_CONFIRMATION_REQUIRED,
        "Write confirmation required",
        "You must type 'WRITE' to confirm this operation.",
    ),
    "backup_recommended": WarningItem.info(
        WarningCode.W_BACKUP_FAILED,
        "Backup recommended before proceeding",
        "Create a backup of your radio configuration before making changes.",
    ),
}
