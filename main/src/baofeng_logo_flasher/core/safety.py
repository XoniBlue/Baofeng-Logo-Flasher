"""
Safety context and write gating for radio operations.

Centralizes all confirmation and gating rules to ensure both CLI and
Streamlit enforce identical safety checks.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Callable

# Confirmation token required for non-interactive writes
CONFIRMATION_TOKEN = "WRITE"


class WritePermissionError(Exception):
    """
    Raised when a write operation is not permitted.

    Attributes:
        reason: Human-readable explanation of why write was denied
        details: Additional context (model, region, etc.)
    """
    def __init__(self, reason: str, details: Optional[dict] = None):
        self.reason = reason
        self.details = details or {}
        super().__init__(reason)


@dataclass
class SafetyContext:
    """
    Safety context for write operations.

    Encapsulates all the information needed to determine whether a
    write operation should be permitted.

    Attributes:
        write_enabled: Whether the --write flag was provided (CLI) or
                      risk acknowledged (Streamlit)
        confirmation_token: For non-interactive mode, must match CONFIRMATION_TOKEN
        interactive: Whether the UI can prompt for confirmation
        model_detected: Detected or specified radio model name
        region_known: Whether the target region is definitively known
        simulate: Whether this is a simulation/dry-run
        warnings: List of warning messages accumulated during operation
    """
    write_enabled: bool = False
    confirmation_token: Optional[str] = None
    interactive: bool = True
    model_detected: str = ""
    region_known: bool = False
    simulate: bool = False
    warnings: List[str] = field(default_factory=list)

    # Callbacks for interactive prompts
    # CLI sets these to prompt functions; Streamlit can use session state
    prompt_confirmation: Optional[Callable[[str], str]] = None
    show_details: Optional[Callable[[dict], None]] = None

    def add_warning(self, message: str) -> None:
        """Add a warning to the context."""
        self.warnings.append(message)

    @property
    def is_model_unknown(self) -> bool:
        """Check if model is unknown or empty."""
        return not self.model_detected or self.model_detected.lower() == "unknown"

    def to_details_dict(
        self,
        target_region: str = "",
        bytes_length: int = 0,
        offset: Optional[int] = None,
    ) -> dict:
        """Create a details dictionary for display."""
        details = {
            "model": self.model_detected or "Unknown",
            "target_region": target_region,
            "bytes_length": bytes_length,
        }
        if offset is not None:
            details["offset"] = f"0x{offset:06X}"
        if self.warnings:
            details["warnings"] = self.warnings
        return details


def require_write_permission(
    ctx: SafetyContext,
    target_region: str = "",
    bytes_length: int = 0,
    offset: Optional[int] = None,
) -> None:
    """
    Enforce write permission rules.

    This is the single gating function that both CLI and Streamlit must use.

    Rules enforced:
    1. If simulate mode: always allowed (no actual write)
    2. If write not enabled: raise with instructions
    3. If model unknown or region unknown: deny unless explicit override exists
    4. If confirmation token present: must match exactly
    5. If interactive: prompt user for confirmation

    Args:
        ctx: Safety context with all required information
        target_region: Description of target memory region
        bytes_length: Number of bytes to write
        offset: Optional offset being written to

    Raises:
        WritePermissionError: If write is not permitted
    """
    details = ctx.to_details_dict(target_region, bytes_length, offset)

    # Rule 1: Simulation mode is always allowed
    if ctx.simulate:
        return

    # Rule 2: Write must be explicitly enabled
    if not ctx.write_enabled:
        raise WritePermissionError(
            "Write operation requires explicit permission. "
            "CLI: use --write flag. "
            "UI: acknowledge risk checkbox.",
            details=details,
        )

    # Rule 3: Cannot write to unknown model
    if ctx.is_model_unknown:
        raise WritePermissionError(
            "Cannot write to radio with unknown model. "
            "Identification failed or model not recognized.",
            details=details,
        )

    # Rule 4: Cannot write to unknown region (unless explicitly accepted)
    # Note: We check region_known only if no explicit region was provided
    # Discovery mode with --accept-discovered bypasses this
    if not ctx.region_known and not target_region:
        raise WritePermissionError(
            "Target region is unknown. Provide explicit offset or "
            "use discovery mode with appropriate flags.",
            details=details,
        )

    # Rule 5: Token-based confirmation for non-interactive
    if ctx.confirmation_token is not None:
        if ctx.confirmation_token.strip().upper() != CONFIRMATION_TOKEN:
            raise WritePermissionError(
                f"Confirmation token mismatch. Expected '{CONFIRMATION_TOKEN}'.",
                details=details,
            )
        # Token matched, permission granted
        return

    # Rule 6: Interactive confirmation required
    if ctx.interactive:
        if ctx.show_details:
            ctx.show_details(details)

        if ctx.prompt_confirmation:
            user_input = ctx.prompt_confirmation(
                f"Type '{CONFIRMATION_TOKEN}' to proceed, or anything else to abort"
            )
            if user_input.strip().upper() != CONFIRMATION_TOKEN:
                raise WritePermissionError(
                    "Confirmation failed. Write aborted by user.",
                    details=details,
                )
        else:
            # No prompt callback set - we cannot confirm interactively
            raise WritePermissionError(
                "Interactive confirmation required but no prompt handler set. "
                "Provide confirmation_token for non-interactive mode.",
                details=details,
            )
    else:
        # Non-interactive but no token provided
        raise WritePermissionError(
            "Non-interactive mode requires confirmation_token.",
            details=details,
        )


def create_cli_safety_context(
    write_flag: bool,
    model: str = "",
    region_known: bool = True,
    simulate: bool = False,
    confirmation_token: Optional[str] = None,
) -> SafetyContext:
    """
    Create a SafetyContext configured for CLI usage.

    If confirmation_token is None and we're in a TTY, sets up interactive prompts.
    """
    import sys

    interactive = sys.stdin.isatty() and confirmation_token is None

    ctx = SafetyContext(
        write_enabled=write_flag,
        confirmation_token=confirmation_token,
        interactive=interactive,
        model_detected=model,
        region_known=region_known,
        simulate=simulate,
    )

    return ctx


def create_streamlit_safety_context(
    risk_acknowledged: bool,
    model: str = "",
    region_known: bool = True,
    simulate: bool = False,
) -> SafetyContext:
    """
    Create a SafetyContext configured for Streamlit usage.

    Streamlit is never interactive in the prompt sense - it uses
    the risk_acknowledged checkbox instead.
    """
    # For Streamlit, we use a token-based approach
    # If risk is acknowledged, we set the token to the expected value
    token = CONFIRMATION_TOKEN if risk_acknowledged else None

    return SafetyContext(
        write_enabled=risk_acknowledged,
        confirmation_token=token,
        interactive=False,  # Streamlit handles confirmation via UI, not prompts
        model_detected=model,
        region_known=region_known,
        simulate=simulate,
    )
