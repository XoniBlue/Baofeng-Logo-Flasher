"""
Reusable Streamlit UI components for Baofeng Logo Flasher.

Provides consistent UI elements across all pages:
- Safety panel with mode switching
- Warning/error display with collapsible sections
- Operation preview and confirmation flow
"""

from typing import List, Optional, Dict, Any, Union
import streamlit as st

from baofeng_logo_flasher.core.messages import (
    MessageLevel,
    WarningCode,
    WarningItem,
    warnings_from_strings,
    result_to_warnings,
    COMMON_WARNINGS,
)
from baofeng_logo_flasher.core.results import OperationResult
from baofeng_logo_flasher.core.safety import SafetyContext, CONFIRMATION_TOKEN


# =============================================================================
# Session State Management
# =============================================================================

def init_write_mode_state() -> None:
    """Initialize session state for write mode management."""
    if "write_mode_enabled" not in st.session_state:
        st.session_state.write_mode_enabled = False
    if "write_confirmation_token" not in st.session_state:
        st.session_state.write_confirmation_token = ""
    if "risk_acknowledged" not in st.session_state:
        st.session_state.risk_acknowledged = False
    if "operation_previewed" not in st.session_state:
        st.session_state.operation_previewed = False


def is_write_enabled() -> bool:
    """Check if write mode is enabled with proper confirmation."""
    init_write_mode_state()
    return (
        st.session_state.write_mode_enabled
        and st.session_state.risk_acknowledged
        and st.session_state.write_confirmation_token.strip().upper() == CONFIRMATION_TOKEN
    )


def get_write_confirmation_token() -> str:
    """Get the current write confirmation token."""
    init_write_mode_state()
    return st.session_state.write_confirmation_token


def reset_write_mode() -> None:
    """Reset write mode to read-only state."""
    st.session_state.write_mode_enabled = False
    st.session_state.write_confirmation_token = ""
    st.session_state.risk_acknowledged = False
    st.session_state.operation_previewed = False


# =============================================================================
# Mode Switch Component
# =============================================================================

def render_mode_switch() -> bool:
    """
    Render the read-only / write-enabled mode switch at the top of the page.

    Returns:
        bool: True if write mode is fully enabled and confirmed
    """
    init_write_mode_state()

    # Mode selector container
    with st.container():
        st.markdown("#### 🔐 Operation Mode")

        col1, col2 = st.columns([1, 2])

        with col1:
            mode_options = ["🔒 Read-Only (Safe)", "✏️ Write Enabled"]
            current_mode = 1 if st.session_state.write_mode_enabled else 0

            selected_mode = st.radio(
                "Select mode",
                options=mode_options,
                index=current_mode,
                key="mode_selector",
                label_visibility="collapsed",
                help="Read-only mode is safe for testing. Write mode requires additional confirmation."
            )

            st.session_state.write_mode_enabled = (selected_mode == mode_options[1])

        with col2:
            if st.session_state.write_mode_enabled:
                st.warning(
                    "⚠️ **Write mode enabled.** Operations may modify your radio. "
                    "Additional confirmation required below."
                )
            else:
                st.info(
                    "ℹ️ **Read-only mode.** All operations are safe. "
                    "No changes will be made to your radio."
                )

        st.divider()

    return is_write_enabled()


# =============================================================================
# Write Confirmation Component
# =============================================================================

def render_write_confirmation(
    operation_name: str = "write operation",
    details: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Render the write confirmation panel with checkbox and typed token.

    Must be used before any write operation. Requires:
    1. Write mode enabled
    2. Risk acknowledgment checkbox
    3. Typed confirmation token (WRITE)
    4. Operation preview visible

    Args:
        operation_name: Name of the operation for display
        details: Optional operation details to preview

    Returns:
        bool: True if all confirmation requirements are met
    """
    init_write_mode_state()

    if not st.session_state.write_mode_enabled:
        st.info("ℹ️ Enable **Write Mode** above to perform write operations.")
        return False

    with st.container():
        st.markdown("#### ✅ Write Confirmation Required")

        # Step 1: Show operation preview
        if details:
            with st.expander("📋 Operation Preview", expanded=True):
                render_operation_preview_details(details)
                st.session_state.operation_previewed = True

        # Step 2: Risk acknowledgment checkbox
        col1, col2 = st.columns(2)

        with col1:
            risk_ack = st.checkbox(
                "**I understand the risks** and have backed up my radio configuration",
                value=st.session_state.risk_acknowledged,
                key="risk_ack_checkbox",
                help="Check this to confirm you understand flashing risks"
            )
            st.session_state.risk_acknowledged = risk_ack

        # Step 3: Typed confirmation
        with col2:
            token = st.text_input(
                f"Type **{CONFIRMATION_TOKEN}** to confirm:",
                value=st.session_state.write_confirmation_token,
                key="confirmation_token_input",
                help=f"You must type exactly '{CONFIRMATION_TOKEN}' to enable write operations"
            )
            st.session_state.write_confirmation_token = token

        # Status indicator
        is_confirmed = is_write_enabled()

        if is_confirmed:
            st.success(f"✅ Confirmation complete. Ready to {operation_name}.")
        else:
            missing = []
            if not st.session_state.risk_acknowledged:
                missing.append("acknowledge risks")
            if st.session_state.write_confirmation_token.strip().upper() != CONFIRMATION_TOKEN:
                missing.append(f"type '{CONFIRMATION_TOKEN}'")
            if missing:
                st.warning(f"⚠️ To proceed, you must: {', '.join(missing)}")

        return is_confirmed


# =============================================================================
# Safety Panel Component
# =============================================================================

def render_safety_panel(
    result_or_ctx: Union[OperationResult, SafetyContext, None] = None,
    show_mode_switch: bool = True,
    show_confirmation: bool = False,
    operation_name: str = "operation",
    details: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Render the complete safety panel used across UI pages.

    Combines mode switch, warnings, and optional confirmation into a
    consistent panel.

    Args:
        result_or_ctx: OperationResult or SafetyContext to extract warnings from
        show_mode_switch: Whether to show the mode switch
        show_confirmation: Whether to show write confirmation section
        operation_name: Name of operation for confirmation
        details: Operation details for preview

    Returns:
        bool: True if write is enabled and confirmed (if show_confirmation=True)
    """
    init_write_mode_state()

    with st.container():
        # Mode switch at top
        if show_mode_switch:
            render_mode_switch()

        # Extract and show warnings
        warnings = []
        if isinstance(result_or_ctx, OperationResult):
            warnings = result_to_warnings(result_or_ctx)
        elif isinstance(result_or_ctx, SafetyContext):
            warnings = warnings_from_strings(result_or_ctx.warnings)

        if warnings:
            render_warning_list(warnings, collapsed_default=False)

        # Confirmation section if needed
        if show_confirmation:
            return render_write_confirmation(operation_name, details)

        return is_write_enabled()


# =============================================================================
# Warning List Component
# =============================================================================

def render_warning_list(
    warnings: List[WarningItem],
    collapsed_default: bool = True,
    title: str = "⚠️ Warnings & Risks",
) -> None:
    """
    Render a list of warnings in a collapsible expander.

    Args:
        warnings: List of WarningItem objects to display
        collapsed_default: Whether expander is collapsed by default
        title: Title for the expander section
    """
    if not warnings:
        return

    # Count by level
    error_count = sum(1 for w in warnings if w.level == MessageLevel.ERROR)
    warn_count = sum(1 for w in warnings if w.level == MessageLevel.WARN)
    info_count = sum(1 for w in warnings if w.level == MessageLevel.INFO)

    # Build title with counts
    counts = []
    if error_count:
        counts.append(f"❌ {error_count} error{'s' if error_count > 1 else ''}")
    if warn_count:
        counts.append(f"⚠️ {warn_count} warning{'s' if warn_count > 1 else ''}")
    if info_count:
        counts.append(f"ℹ️ {info_count} info")

    display_title = f"{title} ({', '.join(counts)})" if counts else title

    # Force open if there are errors
    expanded = not collapsed_default or error_count > 0

    with st.expander(display_title, expanded=expanded):
        for warning in warnings:
            _render_single_warning(warning)


def _render_single_warning(warning: WarningItem) -> None:
    """Render a single warning item."""
    # Choose display method based on level
    if warning.level == MessageLevel.ERROR:
        container = st.error
        icon = "❌"
    elif warning.level == MessageLevel.WARN:
        container = st.warning
        icon = "⚠️"
    else:
        container = st.info
        icon = "ℹ️"

    # Build message
    with st.container():
        # Main warning
        container(f"**{warning.title}**")

        # Detail and remediation in nested expander if present
        if warning.detail or warning.remediation:
            with st.expander(f"Details ({warning.code.value})", expanded=False):
                if warning.detail:
                    st.markdown(warning.detail)
                if warning.remediation:
                    st.markdown(f"**Suggested action:** {warning.remediation}")


# =============================================================================
# Operation Preview Component
# =============================================================================

def render_operation_preview(
    result: OperationResult,
    show_hashes: bool = True,
    title: str = "📊 Operation Details",
) -> None:
    """
    Render operation result as a preview/summary panel.

    Shows model, region, bytes, hashes, and metadata in a structured format.

    Args:
        result: OperationResult to display
        show_hashes: Whether to show hash values
        title: Title for the section
    """
    details = {
        "operation": result.operation,
        "model": result.model,
        "region": result.region,
        "bytes_length": result.bytes_len,
    }

    if show_hashes and result.hashes:
        details["hashes"] = result.hashes

    if result.metadata:
        details["metadata"] = result.metadata

    with st.expander(title, expanded=True):
        render_operation_preview_details(details)

        # Show "would write" summary for dry-run
        if result.metadata.get("simulated") or not result.ok:
            if result.bytes_len > 0:
                st.info(f"**Would write:** {result.bytes_len:,} bytes to {result.region or 'target region'}")


def render_operation_preview_details(details: Dict[str, Any]) -> None:
    """
    Render operation details as a structured display.

    Args:
        details: Dictionary of details to display
    """
    # Core operation info
    col1, col2 = st.columns(2)

    with col1:
        if details.get("model"):
            st.markdown(f"**Model:** `{details['model']}`")
        if details.get("region"):
            st.markdown(f"**Region:** `{details['region']}`")
        if details.get("offset"):
            st.markdown(f"**Offset:** `{details['offset']}`")

    with col2:
        if details.get("bytes_length"):
            st.markdown(f"**Size:** {details['bytes_length']:,} bytes")
        if details.get("operation"):
            st.markdown(f"**Operation:** `{details['operation']}`")

    # Hashes section
    if details.get("hashes"):
        st.markdown("**Hashes:**")
        for name, value in details["hashes"].items():
            if value:
                display_val = value[:16] + "..." if len(value) > 16 else value
                st.code(f"{name}: {display_val}", language=None)

    # Metadata section
    if details.get("metadata"):
        with st.expander("🔧 Technical Details", expanded=False):
            for key, value in details["metadata"].items():
                if key not in ("simulated", "clone_data"):  # Skip large/internal data
                    st.text(f"{key}: {value}")


# =============================================================================
# Status Block Components
# =============================================================================

def render_status_success(
    title: str,
    message: str = "",
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """Render a success status block."""
    st.success(f"✅ **{title}**")
    if message:
        st.markdown(message)
    if details:
        with st.expander("Details", expanded=False):
            render_operation_preview_details(details)


def render_status_error(
    title: str,
    message: str = "",
    details: Optional[Dict[str, Any]] = None,
    warnings: Optional[List[WarningItem]] = None,
) -> None:
    """Render an error status block."""
    st.error(f"❌ **{title}**")
    if message:
        st.markdown(message)
    if warnings:
        render_warning_list(warnings, collapsed_default=False, title="Error Details")
    elif details:
        with st.expander("Error Details", expanded=True):
            render_operation_preview_details(details)


def render_status_warning(
    title: str,
    message: str = "",
) -> None:
    """Render a warning status block."""
    st.warning(f"⚠️ **{title}**")
    if message:
        st.markdown(message)


# =============================================================================
# Feature Navigation Component
# =============================================================================

def render_feature_sidebar() -> Optional[str]:
    """
    Render the feature sidebar navigation.

    Returns:
        Selected feature ID or None
    """
    from baofeng_logo_flasher.features import get_sidebar_navigation, RiskLevel

    st.sidebar.markdown("## 📻 Features")

    nav = get_sidebar_navigation()
    selected = None

    for category, features in nav.items():
        st.sidebar.markdown(f"### {category}")

        for feature in features:
            # Add risk indicator
            risk_icon = ""
            if feature.risk_level == RiskLevel.HIGH:
                risk_icon = " 🚨"
            elif feature.risk_level == RiskLevel.MEDIUM:
                risk_icon = " ⚠️"

            if st.sidebar.button(
                f"{feature.icon} {feature.name}{risk_icon}",
                key=f"nav_{feature.id}",
                use_container_width=True,
            ):
                selected = feature.id

    return selected


# =============================================================================
# Raw Logs Component
# =============================================================================

def render_raw_logs(
    logs: List[str],
    title: str = "📜 Raw Logs",
    collapsed_default: bool = True,
) -> None:
    """
    Render raw log output in a collapsible section.

    Args:
        logs: List of log lines to display
        title: Title for the section
        collapsed_default: Whether to collapse by default
    """
    if not logs:
        return

    with st.expander(title, expanded=not collapsed_default):
        log_text = "\n".join(logs)
        st.code(log_text, language="text")
