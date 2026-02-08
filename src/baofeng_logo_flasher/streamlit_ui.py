"""
Streamlit UI for Baofeng Logo Flasher.

Focused interface for boot logo flashing with tabs for other utilities.

NOTE: This module requires the optional 'ui' extra to be installed:
    pip install -e ".[ui]"
"""

import logging
import sys
import tempfile
from pathlib import Path
from typing import Optional

# Guard streamlit import - it's an optional dependency
try:
    import streamlit as st
    from PIL import Image
except ImportError as e:
    _missing = "streamlit" if "streamlit" in str(e) else str(e)
    print(
        f"\n[ERROR] Missing required package: {_missing}\n\n"
        f"The Streamlit UI requires extra dependencies.\n"
        f"Install them with:\n\n"
        f"    pip install -e \".[ui]\"\n\n"
        f"Or install streamlit directly:\n\n"
        f"    pip install streamlit\n"
    )
    sys.exit(1)

from baofeng_logo_flasher.logo_codec import LogoCodec, BitmapFormat
from baofeng_logo_flasher.logo_patcher import LogoPatcher
from baofeng_logo_flasher.protocol_verifier import ProtocolVerifier
from baofeng_logo_flasher.bitmap_scanner import scan_bytes, save_candidates
from baofeng_logo_flasher.boot_logo import (
    SERIAL_FLASH_CONFIGS,
    convert_bmp_to_raw,
    convert_raw_to_bmp,
    flash_logo as _boot_logo_flash,
    list_serial_ports,
    read_logo,
    read_radio_id,
)

# Import from core module for unified safety and parsing
from baofeng_logo_flasher.core.safety import (
    SafetyContext,
    require_write_permission,
    WritePermissionError,
    create_streamlit_safety_context,
    CONFIRMATION_TOKEN,
)
from baofeng_logo_flasher.core.results import OperationResult
from baofeng_logo_flasher.core.messages import (
    WarningItem,
    WarningCode,
    MessageLevel,
    result_to_warnings,
    COMMON_WARNINGS,
)
from baofeng_logo_flasher.core.actions import flash_logo_serial

# Import model registry for capabilities
from baofeng_logo_flasher.models import (
    list_models as registry_list_models,
    get_model as registry_get_model,
    get_capabilities as registry_get_capabilities,
    SafetyLevel,
)

# Import UI components
from baofeng_logo_flasher.ui.components import (
    render_safety_panel,
    render_warning_list,
    render_operation_preview,
    render_mode_switch,
    render_write_confirmation,
    render_status_success,
    render_status_error,
    render_raw_logs,
    init_write_mode_state,
    is_write_enabled,
)

logger = logging.getLogger(__name__)


def _init_session_state():
    """Initialize session state for persistence."""
    if "selected_model" not in st.session_state:
        st.session_state.selected_model = "UV-5RM"
    if "selected_port" not in st.session_state:
        st.session_state.selected_port = None
    if "simulate_mode" not in st.session_state:
        st.session_state.simulate_mode = True
    # Initialize write mode state from UI components
    init_write_mode_state()


def main():
    """Streamlit app main."""
    st.set_page_config(
        page_title="Baofeng Logo Flasher",
        page_icon="🔧",
        layout="wide",
    )

    _init_session_state()

    # Header
    col1, col2 = st.columns([3, 1])
    with col1:
        st.title("🔧 Baofeng Logo Flasher")
    with col2:
        st.markdown("[![GitHub](https://img.shields.io/badge/GitHub-LogoFlasher-blue)](https://github.com)")

    st.markdown(
        """
        **Safe, fast boot logo flashing for Baofeng UV-5RM & compatible radios.**
        Direct serial protocol with encryption support. Simulation mode for testing.
        """
    )

    # Global safety panel (collapsible)
    render_safety_panel()

    # Main tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "⚡ Boot Logo Flasher",
        "📋 Capabilities",
        "🔧 Tools & Inspect",
        "✓ Verify & Patch"
    ])

    with tab1:
        tab_boot_logo_flasher()

    with tab2:
        tab_capabilities()

    with tab3:
        tab_tools_and_inspect()

    with tab4:
        tab_verify_and_patch()


def launch() -> None:
    """Launch the Streamlit app without requiring a manual CLI command."""
    from streamlit.web import bootstrap

    app_path = str(Path(__file__).resolve())
    bootstrap.run(app_path, "streamlit run", [], {})


# ============================================================================
# TAB: CAPABILITIES
# ============================================================================

def tab_capabilities():
    """Show capabilities report for radio models."""
    import json

    st.markdown("### 📋 Model Capabilities")
    st.markdown(
        """
        View supported operations, safety levels, and configuration for each radio model.
        Select a model or connect a radio to see what operations are available.
        """
    )

    col1, col2 = st.columns([2, 1])

    with col1:
        # Model selector
        models = registry_list_models()
        selected_model = st.selectbox(
            "Select Model",
            models,
            index=models.index("UV-5RM") if "UV-5RM" in models else 0,
            help="Choose a radio model to view its capabilities",
        )

    with col2:
        # JSON export option
        export_json = st.checkbox("Show JSON", help="Display raw JSON for scripting")

    # Get capabilities
    caps = registry_get_capabilities(selected_model)

    if export_json:
        st.json(caps.to_dict())
        return

    # Config summary
    config = registry_get_model(selected_model)
    if config:
        st.markdown("#### Configuration")
        config_cols = st.columns(4)
        with config_cols[0]:
            st.metric("Protocol", config.protocol.value.upper())
        with config_cols[1]:
            st.metric("Baud Rate", f"{config.baud_rate}")
        with config_cols[2]:
            magic_display = config.magic_bytes.decode('ascii', errors='ignore') if len(config.magic_bytes) == 16 else config.magic_bytes.hex().upper()[:16]
            st.metric("Magic", magic_display + ("..." if len(magic_display) >= 16 else ""))
        with config_cols[3]:
            region_count = len(caps.discovered_regions)
            st.metric("Logo Regions", str(region_count) if region_count > 0 else "Unknown")

    st.markdown("---")

    # Capabilities table
    st.markdown("#### Supported Operations")

    cap_data = []
    for cap_info in caps.capabilities:
        safety_emoji = {
            SafetyLevel.SAFE: "✅",
            SafetyLevel.MODERATE: "⚠️",
            SafetyLevel.RISKY: "🔴",
        }.get(cap_info.safety, "❓")

        cap_data.append({
            "Operation": cap_info.capability.name.replace("_", " ").title(),
            "Supported": "✅ Yes" if cap_info.supported else "❌ No",
            "Safety": f"{safety_emoji} {cap_info.safety.value.title()}",
            "Reason": cap_info.reason,
        })

    st.dataframe(cap_data, use_container_width=True, hide_index=True)

    # Logo regions
    if caps.discovered_regions:
        st.markdown("#### Logo Regions")

        region_data = []
        for region in caps.discovered_regions:
            region_data.append({
                "Address": f"0x{region.start_addr:04X} - 0x{region.end_addr:04X}",
                "Dimensions": f"{region.width}x{region.height}",
                "Color Mode": region.color_mode,
                "Encrypted": "Yes" if region.encrypt else "No",
                "Size": f"{region.length:,} bytes",
            })

        st.dataframe(region_data, use_container_width=True, hide_index=True)
    else:
        st.info(
            "📍 **Logo region not mapped for this model.** "
            "Use the 'Tools & Inspect' tab to scan for bitmap regions in a clone image."
        )

    # Notes
    if caps.notes:
        st.markdown("#### Notes")
        for note in caps.notes:
            st.markdown(f"- {note}")

    # All models summary
    with st.expander("📋 All Registered Models"):
        all_models_data = []
        for model_name in registry_list_models():
            cfg = registry_get_model(model_name)
            if cfg:
                region_info = "Unknown"
                if cfg.logo_regions:
                    r = cfg.logo_regions[0]
                    region_info = f"0x{r.start_addr:04X} ({r.width}x{r.height})"

                all_models_data.append({
                    "Model": model_name,
                    "Vendor": cfg.vendor,
                    "Protocol": cfg.protocol.value.upper(),
                    "Baud": cfg.baud_rate,
                    "Logo Region": region_info,
                })

        st.dataframe(all_models_data, use_container_width=True, hide_index=True)


# ============================================================================
# TAB 1: BOOT LOGO FLASHER (Main feature)
# ============================================================================

def _process_image_for_radio(
    img: Image.Image,
    target_size: tuple,
    resize_method: str,
    bg_color: str = "#000000"
) -> Image.Image:
    """
    Process an image for radio flashing.

    Args:
        img: PIL Image to process
        target_size: (width, height) tuple
        resize_method: One of "Fit (letterbox)", "Fill (stretch)", "Crop (center)"
        bg_color: Background color for letterboxing (hex string)

    Returns:
        Processed PIL Image at target_size
    """
    # Convert to RGB if needed
    if img.mode != "RGB":
        # Handle transparency by compositing onto background
        if img.mode in ("RGBA", "LA", "P"):
            background = Image.new("RGB", img.size, bg_color)
            if img.mode == "P":
                img = img.convert("RGBA")
            if img.mode in ("RGBA", "LA"):
                background.paste(img, mask=img.split()[-1])
                img = background
            else:
                img = img.convert("RGB")
        else:
            img = img.convert("RGB")

    if resize_method == "Fill (stretch)":
        # Simple stretch to target size
        return img.resize(target_size, Image.Resampling.LANCZOS)

    elif resize_method == "Crop (center)":
        # Resize to cover target, then center crop
        img_ratio = img.size[0] / img.size[1]
        target_ratio = target_size[0] / target_size[1]

        if img_ratio > target_ratio:
            # Image is wider - resize by height, crop width
            new_height = target_size[1]
            new_width = int(new_height * img_ratio)
        else:
            # Image is taller - resize by width, crop height
            new_width = target_size[0]
            new_height = int(new_width / img_ratio)

        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # Center crop
        left = (new_width - target_size[0]) // 2
        top = (new_height - target_size[1]) // 2
        right = left + target_size[0]
        bottom = top + target_size[1]

        return img.crop((left, top, right, bottom))

    else:  # "Fit (letterbox)" - default
        # Resize to fit within target, letterbox the rest
        img.thumbnail(target_size, Image.Resampling.LANCZOS)

        # Create background and paste centered
        background = Image.new("RGB", target_size, bg_color)
        offset = (
            (target_size[0] - img.size[0]) // 2,
            (target_size[1] - img.size[1]) // 2,
        )
        background.paste(img, offset)
        return background


def tab_boot_logo_flasher():
    """Boot logo flashing via serial connection."""

    st.markdown("### Flash Custom Boot Logo")
    st.markdown(
        "Connect your UV-5RM to a USB cable and flash a custom boot logo directly. "
        "Works via reverse-engineered serial protocol with XOR encryption."
    )

    # Risk banner
    st.error(
        """
        ⚠️ **FLASHING RISK**: If the connection drops during write, your radio may become **unresponsive**.

        **Before flashing:**
        - ✓ Fully charge the radio (USB power recommended)
        - ✓ Use a short, quality USB cable
        - ✓ Close other serial apps (CHIRP, Arduino IDE, etc.)
        - ✓ Have a backup radio or cable on hand

        **Recommended:** Test with **Simulation Mode** first!
        """,
        icon="🚨"
    )

    # Hardware architecture notice for UV-5RM
    st.info(
        """
        **📡 UV-5RM Hardware Info** (from [reverse engineering](https://github.com/amoxu/Baofeng-UV-5RM-5RH-RE)):

        | Component | Details |
        |-----------|---------|
        | MCU | AT32F421C8T7 (64KB flash, 16KB RAM) |
        | External Flash | XMC 25QH16CJIG (16Mbit / 2MB SPI) |
        | RF Chip | BK4819 |

        **Why direct serial flashing may not work:**
        - Boot logos are stored on the **external SPI flash** (2MB chip)
        - The clone protocol only accesses **MCU memory** (channel data, settings)
        - Direct logo modification requires **firmware-level access** to the SPI flash

        **Alternative:** Use the Image Converter tool to prepare your logo, then flash
        using the official Baofeng software or a modified firmware.
        """
    )

    # Two-column layout
    col_left, col_right = st.columns([1.2, 1])

    # ===== LEFT: Configuration =====
    with col_left:
        st.markdown("#### 📡 Configuration")

        # Model selection
        model = st.selectbox(
            "Radio Model",
            list(SERIAL_FLASH_CONFIGS.keys()),
            index=list(SERIAL_FLASH_CONFIGS.keys()).index(st.session_state.selected_model),
            key="model_select",
            help="Select your radio model for correct image size and encryption"
        )
        st.session_state.selected_model = model
        config = dict(SERIAL_FLASH_CONFIGS[model])
        write_addr_mode = config.get("write_addr_mode", "byte")

        st.caption(f"A5 write address mode: {write_addr_mode}")

        st.divider()

        # Serial port selection
        st.markdown("**Serial Port**")
        ports = list_serial_ports()

        if ports:
            # Show available ports with current selection
            port_display = {p: p for p in ports}
            port_display["[Enter manually]"] = "[Enter manually]"

            port_key = ports[0] if ports else "[Enter manually]"
            if st.session_state.selected_port and st.session_state.selected_port in ports:
                port_key = st.session_state.selected_port

            cols_port = st.columns([3, 1])
            with cols_port[0]:
                selected = st.selectbox(
                    "Available ports",
                    options=list(port_display.keys()),
                    index=list(port_display.keys()).index(port_key) if port_key in port_display else 0,
                    key="port_select",
                    label_visibility="collapsed"
                )

            with cols_port[1]:
                if st.button("🔄 Refresh", use_container_width=True):
                    st.rerun()

            if selected == "[Enter manually]":
                port = st.text_input("Enter port path", value="/dev/ttyUSB0", help="e.g., /dev/ttyUSB0, /dev/cu.SLAB_USBtoUART, COM3")
            else:
                port = selected
        else:
            st.warning("No USB serial ports detected. Enter manually below.")
            port = st.text_input("Enter port path", value="/dev/cu.Plser", help="e.g., /dev/cu.Plser")

        st.session_state.selected_port = port

        st.divider()

        # Test connection button
        test_col1, test_col2 = st.columns(2)
        with test_col1:
            if st.button("📋 Read Radio ID", use_container_width=True):
                try:
                    with st.spinner("Connecting..."):
                        radio_id = read_radio_id(port, magic=config["magic"], timeout=3.0)
                    st.success(f"✓ **Radio ID:** `{radio_id}`")
                    st.info(f"✓ Connection verified! Ready to flash.")
                except Exception as exc:
                    st.error(f"Connection failed: {exc}")

        with test_col2:
            if st.button("📡 List Ports", use_container_width=True):
                ports = list_serial_ports()
                if ports:
                    st.info(f"**Found {len(ports)} port(s):**\n" + "\n".join(f"- `{p}`" for p in ports))
                else:
                    st.warning("No serial ports detected")

        st.divider()

        # Backup logo section
        st.markdown("#### 💾 Backup Current Logo")

        # Check if this model supports logo backup
        # UV-5RM stores logo in flash memory which may be write-only
        is_flash_based = len(config.get("magic", b"")) == 16  # UV17Pro protocol = flash-based

        if is_flash_based:
            st.warning(
                "⚠️ **Note:** UV-5RM and similar radios store the boot logo in flash memory "
                "which may not be readable via the clone protocol. "
                "If backup fails, consider using CHIRP to save a full radio backup."
            )

        backup_col1, backup_col2 = st.columns([3, 1])

        with backup_col1:
            st.markdown("Download the current boot logo from your radio for backup before flashing a new one.")

        with backup_col2:
            backup_simulate = st.checkbox("Simulate", value=True, key="backup_simulate", help="Test without radio")

        if st.button("⬇️ Download Current Logo", use_container_width=True):
            _do_download_logo(port, config, backup_simulate)

    # ===== RIGHT: Image Preview =====
    with col_right:
        st.markdown("#### 🖼️ Boot Logo Image")

        uploaded_file = st.file_uploader(
            "Upload image",
            type=["bmp", "png", "jpg", "jpeg", "gif", "webp", "tiff"],
            key="boot_logo_image",
            help=f"Any image format accepted. Will be resized to {config['size'][0]}×{config['size'][1]} pixels."
        )

        # Track processed image in session state
        if "processed_bmp" not in st.session_state:
            st.session_state.processed_bmp = None

        bmp_file = None  # Will hold the processed BMP data

        if uploaded_file:
            try:
                original_img = Image.open(uploaded_file)
                expected_size = config["size"]

                # Show original image info
                st.caption(f"Original: {original_img.size[0]}×{original_img.size[1]} ({original_img.format or 'Unknown'})")

                # Resize options
                with st.expander("⚙️ Resize Options", expanded=original_img.size != expected_size):
                    resize_method = st.radio(
                        "Resize method",
                        ["Fit (letterbox)", "Fill (stretch)", "Crop (center)"],
                        index=0,
                        horizontal=True,
                        help="How to handle aspect ratio differences"
                    )

                    if resize_method == "Fit (letterbox)":
                        bg_color = st.color_picker("Background color", "#000000", help="Color for letterbox bars")
                    else:
                        bg_color = "#000000"

                # Process the image
                processed_img = _process_image_for_radio(original_img, expected_size, resize_method, bg_color)

                # Show before/after
                col_before, col_after = st.columns(2)
                with col_before:
                    st.image(original_img, caption="Original", use_column_width=True)
                with col_after:
                    st.image(processed_img, caption=f"Processed ({expected_size[0]}×{expected_size[1]})", use_column_width=True)

                if processed_img.size == expected_size:
                    st.success(f"✓ Ready to flash: {expected_size[0]}×{expected_size[1]}")

                # Convert to BMP bytes for flashing
                import io
                bmp_buffer = io.BytesIO()
                processed_img.save(bmp_buffer, format="BMP")
                bmp_buffer.seek(0)
                st.session_state.processed_bmp = bmp_buffer.getvalue()

                # Create a file-like object for the flash function
                class BMPFile:
                    def __init__(self, data):
                        self._data = data
                    def getvalue(self):
                        return self._data
                    def read(self):
                        return self._data

                bmp_file = BMPFile(st.session_state.processed_bmp)

                # Download processed BMP button
                st.download_button(
                    "💾 Download Processed BMP",
                    data=st.session_state.processed_bmp,
                    file_name="boot_logo_processed.bmp",
                    mime="image/bmp",
                    use_container_width=True,
                )

            except Exception as exc:
                st.error(f"Image processing error: {exc}")
                bmp_file = None
        else:
            st.info("📤 Upload any image (PNG, JPG, BMP, etc.)")

    st.divider()

    # ===== Experimental Warning =====
    is_flash_based = len(config.get("magic", b"")) == 16  # UV17Pro protocol
    if is_flash_based:
        with st.expander("⚠️ UV-5RM Hardware Limitation", expanded=False):
            st.warning(
                """
                Direct serial flashing to UV-5RM **will likely fail** because:
                - Boot logos are stored on **external 2MB SPI flash** (not MCU memory)
                - The clone protocol can only access **MCU internal memory**
                - The radio returns 'R' (0x52) = memory not accessible

                **This is a hardware limitation**, not a bug. The boot logo chip is separate
                from the memory accessible via the serial programming cable.

                **Your options:**
                1. Use the **Image Converter** tool to prepare a compatible BMP
                2. Flash via official Baofeng software (if it supports logo changes)
                3. Modify firmware to embed your logo (advanced, requires RE work)
                """
            )

    # ===== Operation Mode & Safety Panel =====
    st.markdown("---")

    # Note: Mode switch is rendered in the global safety panel at the top of the page
    # so we don't duplicate it here

    # Simulation mode option
    simulate = st.checkbox(
        "🧪 Simulation Mode",
        value=st.session_state.simulate_mode,
        help="Test without writing to radio (safe to try multiple times)"
    )
    st.session_state.simulate_mode = simulate

    # Build operation preview details
    operation_details = {
        "model": model,
        "region": f"0x{config.get('start_addr', 0):04X}",
        "bytes_length": config["size"][0] * config["size"][1] * 3,
        "operation": "flash_logo_serial",
        "write_addr_mode": config.get("write_addr_mode", "byte"),
    }

    debug_bytes = st.checkbox(
        "🧰 Protocol Debug Bytes",
        value=False,
        help="Dump payload/frame artifacts to out/streamlit_logo_debug for verification",
    )

    # Write confirmation (only if not simulating)
    if not simulate:
        write_confirmed = render_write_confirmation(
            operation_name="flash boot logo",
            details=operation_details,
        )
    else:
        write_confirmed = True  # Simulation doesn't need confirmation

    st.divider()

    # ===== MAIN Flash Button =====
    can_flash = bmp_file and port and (simulate or write_confirmed)

    if st.button(
        "🚀 Connect & Flash Logo" if not simulate else "🧪 Simulate Flash",
        type="primary",
        use_container_width=True,
        disabled=not can_flash,
        help="Click to begin flashing process"
    ):
        if not bmp_file:
            st.error("❌ Please upload a BMP file")
        elif not port:
            st.error("❌ Please enter a serial port")
        elif not simulate and not write_confirmed:
            st.error("❌ Write confirmation required. Complete the confirmation steps above.")
        else:
            _do_flash(
                port,
                bmp_file,
                config,
                simulate,
                write_confirmed,
                model,
                debug_bytes=debug_bytes,
            )


def _do_flash(
    port: str,
    bmp_file,
    config: dict,
    simulate: bool,
    write_confirmed: bool,
    model: str,
    debug_bytes: bool = False,
):
    """Execute the flash operation using core safety module."""
    bmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".bmp", delete=False) as tmp:
            tmp.write(bmp_file.getvalue())
            bmp_path = tmp.name

        st.markdown("---")

        # Create safety context using core module
        safety_ctx = create_streamlit_safety_context(
            risk_acknowledged=write_confirmed,
            model=model,
            region_known=True,  # We use model config addresses
            simulate=simulate,
        )

        # Progress tracking
        progress_placeholder = st.empty()
        status_placeholder = st.empty()

        bytes_written = [0]

        def _progress_cb(written: int, total: int) -> None:
            pct = min(int((written / total) * 100), 100)
            bytes_written[0] = written
            with progress_placeholder.container():
                st.progress(pct)
            with status_placeholder.container():
                st.text(f"Progress: {written:,} / {total:,} bytes ({pct}%)")

        with st.spinner("🔄 Flashing boot logo..." if not simulate else "🧪 Simulating flash..."):
            # Use core module for flash with safety gating
            result = flash_logo_serial(
                port=port,
                bmp_path=bmp_path,
                config=config,
                safety_ctx=safety_ctx,
                progress_cb=_progress_cb if not simulate else None,
                debug_bytes=debug_bytes,
                debug_output_dir="out/streamlit_logo_debug",
            )

        # Success output
        st.markdown("---")
        if not result.ok:
            raise Exception("\n".join(result.errors))

        if simulate or result.metadata.get("simulated"):
            result_msg = result.metadata.get("result_message", "Simulation complete")
            st.info(f"✓ **Simulation complete:**\n{result_msg}")
            st.success("Ready for real flashing when you are!")
        else:
            st.balloons()
            result_msg = result.metadata.get("result_message", "Flash successful!")
            st.success(f"✅ **Flash successful!**\n{result_msg}")
            st.info(
                """
                **Next steps:**
                1. Radio should reboot automatically
                2. Check if new boot logo appears on startup
                3. If not, try power cycling the radio
                4. Close serial port in this app before using other tools
                """
            )

        if debug_bytes:
            st.caption("Debug artifacts: out/streamlit_logo_debug")

        # Show any warnings from the operation
        if result.warnings:
            structured_warnings = result_to_warnings(result)
            render_warning_list(structured_warnings, collapsed=True)

        # Show raw logs if present
        if result.logs:
            render_raw_logs(result.logs)

    except WritePermissionError as e:
        render_status_error(f"Write not permitted: {e.reason}")
        if e.details:
            st.info(f"Details: Model={e.details.get('model', 'Unknown')}, "
                   f"Region={e.details.get('target_region', 'Unknown')}")
    except Exception as exc:
        error_msg = str(exc)
        st.error(f"❌ **Flash failed:**\n{error_msg}")

        # Provide helpful context for common errors
        if "Write failed" in error_msg:
            # Check for known response codes
            is_read_only = "0x52" in error_msg or "'R'" in error_msg

            if is_read_only:
                st.warning(
                    """
                    **⚠️ Boot Logo Address Not Accessible**

                    The radio returned 'R' (0x52), indicating the boot logo memory region
                    is **read-only** or the address (0x1000) is incorrect for your firmware.

                    **This is expected behavior** - the boot logo location varies between
                    firmware versions and is not documented. Direct serial flashing of boot
                    logos may not be supported on your specific radio.
                    """
                )

            st.info(
                """
                **Recommended Alternative: Use CHIRP**

                The most reliable method to change the boot logo on UV-5RM radios:

                1. **Download clone image** from your radio using CHIRP
                2. **Use our Image Converter** tool to create a compatible BMP
                3. **Patch the clone file** using the patch-logo command:
                   ```
                   baofeng-logo-flasher patch-logo clone.img logo.bmp --offset 0x5A0
                   ```
                4. **Upload patched clone** back to radio via CHIRP

                The correct boot logo offset in your clone file can be discovered using:
                ```
                baofeng-logo-flasher scan-bitmaps clone.img
                ```
                """
            )
    finally:
        if bmp_path:
            Path(bmp_path).unlink(missing_ok=True)
        logger.exception("Boot logo flash error")


def _do_download_logo(port: str, config: dict, simulate: bool):
    """Execute the download/backup logo operation."""
    try:
        st.markdown("---")

        # Progress tracking
        progress_placeholder = st.empty()
        status_placeholder = st.empty()

        def _progress_cb(read_bytes: int, total: int) -> None:
            pct = min(int((read_bytes / total) * 100), 100)
            with progress_placeholder.container():
                st.progress(pct)
            with status_placeholder.container():
                st.text(f"Progress: {read_bytes:,} / {total:,} bytes ({pct}%)")

        with st.spinner("📥 Reading boot logo..." if not simulate else "🧪 Simulating read..."):
            raw_data, radio_id = read_logo(
                port,
                config,
                simulate=simulate,
                progress_cb=_progress_cb if not simulate else None,
            )

        # Convert to BMP
        bmp_data = convert_raw_to_bmp(raw_data, config)

        # Success output and download button
        st.markdown("---")
        if simulate:
            st.info(f"✓ **Simulation complete:** Would read {len(raw_data):,} bytes")
            st.success("Ready for real download when you are!")
        else:
            st.success(f"✅ **Download successful!** Radio: {radio_id}")
            st.info(f"Read {len(raw_data):,} bytes from address 0x{config['start_addr']:04X}")

        # Provide download button for the BMP file
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"boot_logo_backup_{timestamp}.bmp"

        st.download_button(
            label="💾 Save Boot Logo (BMP)",
            data=bmp_data,
            file_name=filename,
            mime="image/bmp",
            use_container_width=True,
        )

        # Also show a preview
        try:
            import io
            from PIL import Image
            img = Image.open(io.BytesIO(bmp_data))
            st.image(img, caption=f"Downloaded logo ({img.size[0]}×{img.size[1]})", use_column_width=True)
        except Exception:
            pass  # Preview is optional

    except Exception as exc:
        error_msg = str(exc)
        st.error(f"❌ **Download failed:**\n{error_msg}")

        # Provide helpful context for common errors
        if "Incomplete response" in error_msg or "Invalid response" in error_msg:
            st.info(
                """
                **Why this happens:**

                Some radios (like UV-5RM) store the boot logo in flash memory that cannot
                be read using the standard clone protocol. The radio only supports *writing*
                new logos to this memory area.

                **Alternatives:**
                - Use CHIRP to create a full radio backup before flashing
                - You can still flash a new logo without backing up the original
                """
            )
        logger.exception("Boot logo download error")


# ============================================================================
# TAB 2: TOOLS & INSPECT
# ============================================================================

def tab_tools_and_inspect():
    """Tools and image inspection utilities."""

    st.markdown("### Inspection & Scanning Tools")
    st.markdown("Analyze images, scan for logo candidates, and troubleshoot.")

    sub_col1, sub_col2 = st.columns(2)

    with sub_col1:
        st.markdown("#### 🔍 Inspect Clone Image")
        st.markdown("Analyze file structure and safety metrics")

        img_file = st.file_uploader("Upload .img file", type="img", key="inspect_img")
        if img_file:
            data = img_file.getvalue()

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Size", f"{len(data):,} bytes")
            with col2:
                import hashlib
                h = hashlib.sha256(data).hexdigest()
                st.metric("SHA256", h[:12] + "...")
            with col3:
                import math
                freq = {}
                for b in data:
                    freq[b] = freq.get(b, 0) + 1
                entropy = sum(-(count / len(data)) * math.log2(count / len(data))
                            for count in freq.values() if count > 0)
                st.metric("Entropy", f"{entropy:.2f}")

            with st.expander("Raw hex preview"):
                st.code(data[:256].hex(), language="text")

    with sub_col2:
        st.markdown("#### 🔎 Scan for Logo Candidates")
        st.markdown("Find potential logo blocks in an image")

        scan_img = st.file_uploader("Upload .img file", type="img", key="scan_img")
        max_cand = st.slider("Max candidates", 1, 50, 20)
        step = st.slider("Scan step (bytes)", 1, 256, 16)

        if st.button("Scan Image", use_container_width=True):
            if scan_img:
                with st.spinner("Scanning..."):
                    candidates = scan_bytes(scan_img.getvalue(), max_candidates=max_cand, step=step)

                if candidates:
                    st.success(f"Found {len(candidates)} candidates")
                    cols = st.columns(2)
                    for idx, cand in enumerate(candidates[:4]):
                        caption = (f"0x{cand['offset']:05X} | {cand['width']}×{cand['height']} | "
                                 f"{cand['fill_ratio']*100:.0f}% full")
                        with cols[idx % 2]:
                            st.image(cand["image"], caption=caption, use_column_width=True)
                else:
                    st.warning("No candidates found")

    # Image Converter Tool
    st.divider()
    st.markdown("#### 🖼️ Image Converter")
    st.markdown("Convert any image to a radio-compatible BMP file.")

    conv_col1, conv_col2 = st.columns(2)

    with conv_col1:
        # Model selection for size
        conv_model = st.selectbox(
            "Target radio model",
            list(SERIAL_FLASH_CONFIGS.keys()),
            key="conv_model_select",
            help="Select radio to determine output dimensions"
        )
        conv_config = SERIAL_FLASH_CONFIGS[conv_model]
        target_size = conv_config["size"]
        st.caption(f"Output size: {target_size[0]}×{target_size[1]} pixels")

        # Resize options
        conv_resize = st.radio(
            "Resize method",
            ["Fit (letterbox)", "Fill (stretch)", "Crop (center)"],
            index=0,
            key="conv_resize",
            help="How to handle aspect ratio differences"
        )

        if conv_resize == "Fit (letterbox)":
            conv_bg = st.color_picker("Background", "#000000", key="conv_bg")
        else:
            conv_bg = "#000000"

    with conv_col2:
        conv_file = st.file_uploader(
            "Upload image to convert",
            type=["bmp", "png", "jpg", "jpeg", "gif", "webp", "tiff"],
            key="conv_image",
        )

        if conv_file:
            try:
                conv_img = Image.open(conv_file)
                st.caption(f"Input: {conv_img.size[0]}×{conv_img.size[1]} ({conv_img.format or 'Unknown'})")

                # Process
                processed = _process_image_for_radio(conv_img, target_size, conv_resize, conv_bg)

                # Preview
                st.image(processed, caption=f"Output: {target_size[0]}×{target_size[1]}", use_column_width=True)

                # Convert to BMP bytes
                import io
                conv_buffer = io.BytesIO()
                processed.save(conv_buffer, format="BMP")
                conv_bytes = conv_buffer.getvalue()

                # Download
                st.download_button(
                    "💾 Download BMP",
                    data=conv_bytes,
                    file_name=f"boot_logo_{conv_model.replace(' ', '_').lower()}.bmp",
                    mime="image/bmp",
                    use_container_width=True,
                )
            except Exception as e:
                st.error(f"Conversion error: {e}")


# ============================================================================
# TAB 3: VERIFY & PATCH
# ============================================================================

def tab_verify_and_patch():
    """Image verification and offline patching."""

    st.markdown("### Image Patching & Verification")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### ✓ Verify Safety")
        st.markdown("Check image before flashing")

        verify_img = st.file_uploader("Clone .img file", type="img", key="verify_img")
        if verify_img:
            img_path = None
            try:
                with tempfile.NamedTemporaryFile(suffix=".img", delete=False) as tmp:
                    tmp.write(verify_img.getvalue())
                    img_path = tmp.name

                result = ProtocolVerifier.verify_before_write(img_path)

                for check, passed in result['checks'].items():
                    icon = "✓" if passed else "✗"
                    st.write(f"{icon} {check}")

                if result['safe_to_write']:
                    st.success("✓ Safe to write")
                else:
                    st.error("❌ Not safe to write")

                if result['blocking_issues']:
                    st.error("**Issues:**")
                    for issue in result['blocking_issues']:
                        st.write(f"• {issue}")
            finally:
                if img_path:
                    Path(img_path).unlink(missing_ok=True)

    with col2:
        st.markdown("#### 🖌️ Patch Logo (Offline)")
        st.markdown("Modify clone image without radio connection")

        patch_img = st.file_uploader("Clone .img file", type="img", key="patch_img")
        logo_patch = st.file_uploader("Logo image", type=["png", "jpg", "jpeg"], key="patch_logo")

        if logo_patch:
            st.image(Image.open(logo_patch), width=200, caption="Logo preview")

        if st.button("Patch Image", use_container_width=True):
            if patch_img and logo_patch:
                img_path = None
                logo_path = None
                try:
                    with tempfile.NamedTemporaryFile(suffix=".img", delete=False) as tmp:
                        tmp.write(patch_img.getvalue())
                        img_path = tmp.name

                    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                        tmp.write(logo_patch.getvalue())
                        logo_path = tmp.name

                    # Patch (simple offset 0x0000)
                    patcher = LogoPatcher()
                    result = patcher.patch_image(img_path, 0x0000, Image.open(logo_path).tobytes())

                    patched_data = Path(img_path).read_bytes()
                    st.download_button(
                        "⬇️ Download Patched Image",
                        data=patched_data,
                        file_name="clone_patched.img",
                        mime="application/octet-stream"
                    )
                    st.success("✓ Patched successfully")

                except Exception as e:
                    st.error(f"Patch failed: {e}")
                finally:
                    if img_path:
                        Path(img_path).unlink(missing_ok=True)
                    if logo_path:
                        Path(logo_path).unlink(missing_ok=True)
            else:
                st.warning("Please upload both files")


if __name__ == "__main__":
    main()
