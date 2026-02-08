"""
Streamlit UI for Baofeng Logo Flasher.

Focused interface for boot logo flashing with tabs for other utilities.

NOTE: This module requires the optional 'ui' extra to be installed:
    pip install -e ".[ui]"
"""

import logging
import sys
import tempfile
import time
from datetime import datetime
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
    WritePermissionError,
    create_streamlit_safety_context,
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
    render_warning_list,
    render_status_error,
    render_raw_logs,
    init_write_mode_state,
)

logger = logging.getLogger(__name__)

BOOT_IMAGE_MAX_UPLOAD_MB = 10
BOOT_IMAGE_MAX_UPLOAD_BYTES = BOOT_IMAGE_MAX_UPLOAD_MB * 1024 * 1024


def _init_session_state():
    """Initialize session state for persistence."""
    if "selected_model" not in st.session_state:
        st.session_state.selected_model = "UV-5RM"
    if "selected_port" not in st.session_state:
        st.session_state.selected_port = None
    if "simulate_mode" not in st.session_state:
        st.session_state.simulate_mode = True
    if "auto_probe_radio" not in st.session_state:
        st.session_state.auto_probe_radio = True
    if "connection_probe" not in st.session_state:
        st.session_state.connection_probe = {}
    if "connection_poll_meta" not in st.session_state:
        st.session_state.connection_poll_meta = {"last_probe_ts": 0.0, "interval_sec": 4.0}
    if "connection_freeze_polling" not in st.session_state:
        st.session_state.connection_freeze_polling = False
    if "connection_freeze_target" not in st.session_state:
        st.session_state.connection_freeze_target = {"model": None, "port": None}
    if "connection_show_controls" not in st.session_state:
        st.session_state.connection_show_controls = False
    if "connection_last_ready" not in st.session_state:
        st.session_state.connection_last_ready = None
    # Initialize write mode state from UI components
    init_write_mode_state()


def main():
    """Streamlit app main."""
    st.set_page_config(
        page_title="Baofeng UV Logo Flasher",
        page_icon="📡",
        layout="wide",
    )

    _init_session_state()

    st.markdown(
        """
        <style>
        /* Global shell */
        .stApp {
            background:
                radial-gradient(1200px 620px at 12% -10%, rgba(25, 52, 112, 0.18), rgba(0, 0, 0, 0) 45%),
                radial-gradient(900px 520px at 98% -5%, rgba(16, 90, 72, 0.15), rgba(0, 0, 0, 0) 40%),
                linear-gradient(180deg, #020913 0%, #050d19 100%);
        }
        [data-testid="stAppViewContainer"] > .main > div {
            padding-top: 1.35rem;
        }
        section.main > div.block-container {
            max-width: 1180px;
            padding-top: 0.3rem;
            padding-bottom: 1.5rem;
        }

        /* Typography */
        h1, h2, h3, h4 {
            letter-spacing: 0.01em;
        }
        h2, h3 {
            font-weight: 700;
        }
        p, label, .stMarkdown, .stCaption {
            line-height: 1.35;
        }

        /* Hero */
        .hero-wrap {
            margin: 0.25rem auto 0.9rem auto;
            max-width: 980px;
            text-align: center;
            padding: 1.1rem 1.2rem;
            border-radius: 14px;
            background: linear-gradient(120deg, rgba(20,32,58,0.62), rgba(14,46,40,0.48));
            border: 1px solid rgba(255,255,255,0.10);
        }
        .hero-title {
            margin: 0;
            font-size: clamp(1.85rem, 3.6vw, 3rem);
            font-weight: 800;
            letter-spacing: 0.01em;
            line-height: 1.15;
        }
        .hero-sub {
            margin-top: 0.4rem;
            opacity: 0.86;
            font-size: 1rem;
        }
        .hero-sub a {
            color: #7db7ff;
            text-decoration: none;
        }
        .hero-sub a:hover { text-decoration: underline; }
        .hero-repo {
            margin-top: 0.5rem;
        }

        /* Tabs */
        [data-testid="stTabs"] button[role="tab"] {
            border-radius: 10px 10px 0 0;
            padding: 0.55rem 0.9rem;
            margin-right: 0.25rem;
            background: rgba(255,255,255,0.02);
        }
        [data-testid="stTabs"] button[aria-selected="true"] {
            background: rgba(19, 120, 89, 0.16);
            border-bottom: 2px solid rgba(70, 231, 165, 0.6);
        }

        /* Cards/expanders/forms */
        [data-testid="stExpander"] {
            border-radius: 12px;
            border: 1px solid rgba(255,255,255,0.10);
            background: linear-gradient(180deg, rgba(255,255,255,0.03), rgba(255,255,255,0.015));
        }
        [data-testid="stForm"] {
            border-radius: 12px;
            border: 1px solid rgba(255,255,255,0.10);
            background: linear-gradient(180deg, rgba(255,255,255,0.03), rgba(255,255,255,0.015));
            padding: 0.7rem 0.8rem;
        }

        /* Inputs */
        [data-testid="stSelectbox"] > div,
        [data-testid="stTextInput"] > div,
        [data-testid="stFileUploader"] > div {
            border-radius: 10px;
        }
        [data-testid="stFileUploaderDropzone"] {
            border: 1px dashed rgba(120, 173, 255, 0.35);
            border-radius: 12px;
            background: rgba(40, 66, 120, 0.10);
        }

        /* Buttons */
        .stButton > button,
        .stDownloadButton > button {
            border-radius: 10px;
        }
        .stButton > button[kind="primary"] {
            background: linear-gradient(180deg, #1ba579 0%, #178b67 100%);
            border: 1px solid rgba(120,255,208,0.35);
        }

        /* Alerts */
        [data-testid="stAlert"] {
            border-radius: 12px;
        }

        /* Connection status chip tooltip */
        .conn-chip {
            position: relative;
        }
        .conn-chip-info {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 18px;
            height: 18px;
            margin-left: 8px;
            border-radius: 999px;
            border: 1px solid rgba(255,255,255,0.38);
            color: rgba(255,255,255,0.90);
            font-size: 12px;
            font-weight: 700;
            line-height: 1;
            cursor: default;
            vertical-align: middle;
        }
        .conn-chip-tip {
            position: absolute;
            left: 12px;
            top: calc(100% + 9px);
            z-index: 20;
            min-width: 260px;
            max-width: 360px;
            padding: 10px 12px;
            border-radius: 10px;
            border: 1px solid rgba(255,255,255,0.18);
            background: rgba(9, 16, 28, 0.97);
            color: #e6eef8;
            box-shadow: 0 10px 28px rgba(0, 0, 0, 0.38);
            opacity: 0;
            transform: translateY(-4px);
            pointer-events: none;
            transition: opacity 120ms ease, transform 120ms ease;
            white-space: normal;
            font-weight: 500;
            font-size: 0.9rem;
            line-height: 1.35;
        }
        .conn-chip-info:hover .conn-chip-tip {
            opacity: 1;
            transform: translateY(0);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <div class="hero-wrap">
            <h1 class="hero-title">📡 Baofeng UV Logo Flasher</h1>
            <div class="hero-sub">Fast boot-logo flashing for UV-5RM and UV-17-family radios</div>
            <div class="hero-repo">
                <a href="https://github.com/XoniBlue/Baofeng-Logo-Flasher" target="_blank">
                    <img alt="GitHub XoniBlue/Baofeng-Logo-Flasher" src="https://img.shields.io/badge/GitHub-XoniBlue%2FBaofeng--Logo--Flasher-3b82f6"/>
                </a>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Main tabs
    tab1, tab2 = st.tabs([
        "⚡ Boot Logo Flasher",
        "📋 Capabilities",
    ])

    with tab1:
        tab_boot_logo_flasher()

    with tab2:
        tab_capabilities()

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
            "Logo offsets are model/firmware specific and may require external analysis."
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


def _image_to_bmp_bytes(img: Image.Image) -> bytes:
    """Convert a PIL image to BMP bytes."""
    import io

    buf = io.BytesIO()
    img.save(buf, format="BMP")
    return buf.getvalue()


def _last_flash_backup_path(model: str) -> Path:
    """Return path for last flashed logo backup file for a model."""
    safe_model = model.replace(" ", "_").replace("/", "_").lower()
    return Path("backups") / "last_flash" / f"{safe_model}.bmp"


def _save_last_flash_backup(model: str, bmp_bytes: bytes) -> Path:
    """Persist last successful flashed BMP for user recovery/download."""
    out_path = _last_flash_backup_path(model)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(bmp_bytes)
    meta_path = out_path.with_suffix(".json")
    meta_path.write_text(
        (
            "{\n"
            f'  "model": "{model}",\n'
            f'  "saved_at": "{datetime.utcnow().isoformat()}Z",\n'
            f'  "bytes": {len(bmp_bytes)}\n'
            "}\n"
        ),
        encoding="utf-8",
    )
    return out_path


def _probe_connection_status(port: str, model: str, config: dict, force: bool = False) -> dict:
    """Probe radio availability and cache short-lived status in session state."""
    now = time.time()
    cache = st.session_state.connection_probe
    same_target = cache.get("port") == port and cache.get("model") == model
    fresh = now - float(cache.get("ts", 0)) < 5.0
    if not force and same_target and fresh:
        return cache

    protocol = "uv17pro" if config.get("protocol") == "a5_logo" else "uv5r"
    try:
        radio_id = read_radio_id(
            port,
            magic=config.get("magic"),
            baudrate=int(config.get("baudrate", 115200)),
            timeout=min(float(config.get("timeout", 2.0)), 1.5),
            protocol=protocol,
        )
        cache = {
            "port": port,
            "model": model,
            "ts": now,
            "ok": True,
            "radio_id": radio_id,
            "error": "",
        }
    except Exception as exc:
        cache = {
            "port": port,
            "model": model,
            "ts": now,
            "ok": False,
            "radio_id": "",
            "error": str(exc),
        }

    st.session_state.connection_probe = cache
    return cache


def _connection_light(ports: list[str], port: str, probe: dict) -> tuple[str, str]:
    """Return a unified connection indicator icon + label."""
    port_detected = bool(port and ((not ports) or (port in ports)))
    radio_ok = bool(probe.get("ok"))
    if port_detected and radio_ok:
        return "🟢", "Ready to flash (auto-detected)"
    if port_detected:
        return "🟡", "Port found, radio not discovered"
    return "🔴", "Not connected"


def _status_chip(
    icon: str,
    label: str,
    detail: str,
    tone: str,
    tooltip_rows: Optional[list[str]] = None,
) -> None:
    """Render a compact status chip row."""
    palette = {
        "good": ("#0f3d2e", "#67e8a5"),
        "warn": ("#4a3a0f", "#facc15"),
        "bad": ("#4a1111", "#fca5a5"),
    }
    bg, fg = palette.get(tone, palette["warn"])
    detail_html = f"<span style='opacity:0.9;font-weight:400;'> · {detail}</span>" if detail else ""
    tooltip_html = ""
    if tooltip_rows:
        rows = "<br/>".join(tooltip_rows)
        tooltip_html = (
            "<span class='conn-chip-info' aria-label='Connection details'>i"
            f"<span class='conn-chip-tip'>{rows}</span>"
            "</span>"
        )
    st.markdown(
        (
            f"<div class='conn-chip' style='padding:10px 14px;border-radius:12px;background:{bg};"
            f"border:1px solid rgba(255,255,255,0.12);color:{fg};font-weight:600;'>"
            f"{icon} {label}{detail_html}{tooltip_html}</div>"
        ),
        unsafe_allow_html=True,
    )


def _step3_mode_badge(model: str, payload_bytes: int, addr_mode: str, write_mode: bool, debug_mode: bool) -> None:
    """Render a unified Step 3 status badge."""
    if write_mode:
        bg = "rgba(123, 34, 34, 0.24)"
        fg = "#fca5a5"
        border = "rgba(248, 113, 113, 0.36)"
        mode_label = "LIVE WRITE"
    else:
        bg = "rgba(24, 58, 112, 0.22)"
        fg = "#93c5fd"
        border = "rgba(96, 165, 250, 0.32)"
        mode_label = "SIMULATION"

    debug_label = " · DEBUG ON" if debug_mode else ""
    meta = f"{model} · {payload_bytes:,} bytes · {addr_mode}"
    st.markdown(
        (
            f"<div style='padding-top:0.62rem;text-align:right;'>"
            f"<span style='display:inline-block;padding:8px 12px;border-radius:10px;"
            f"background:{bg};border:1px solid {border};color:{fg};font-weight:700;'>"
            f"{mode_label}{debug_label}"
            f"<span style='opacity:0.82;font-weight:500;'> · {meta}</span>"
            f"</span></div>"
        ),
        unsafe_allow_html=True,
    )


@st.fragment(run_every="2s")
def _render_connection_health(model: str, config: dict, port: str, ports: list[str]) -> dict:
    """
    Unified live connection status with adaptive polling.

    Poll cadence:
    - 4s while disconnected/not discovered
    - 12s when fully connected and discovered
    """
    probe = st.session_state.connection_probe

    freeze_target = st.session_state.connection_freeze_target
    target_changed = freeze_target.get("model") != model or freeze_target.get("port") != port
    if target_changed:
        st.session_state.connection_freeze_polling = False
        st.session_state.connection_freeze_target = {"model": model, "port": port}

    now = time.time()
    last_probe = float(st.session_state.connection_poll_meta.get("last_probe_ts", 0.0))
    interval = float(st.session_state.connection_poll_meta.get("interval_sec", 4.0))

    if probe.get("ok") and port and ((not ports) or (port in ports)):
        interval = 12.0
    else:
        interval = 4.0
    st.session_state.connection_poll_meta["interval_sec"] = interval

    should_probe = (
        not st.session_state.connection_freeze_polling
        and port
        and ((not ports) or (port in ports))
        and (now - last_probe >= interval)
    )
    if should_probe:
        probe = _probe_connection_status(port, model, config, force=True)
        st.session_state.connection_poll_meta["last_probe_ts"] = now
    elif not port:
        probe = {"ok": False, "radio_id": "", "error": "No port selected"}
    elif ports and port not in ports:
        probe = {"ok": False, "radio_id": "", "error": "Selected port is not currently detected"}

    icon, label = _connection_light(ports, port, probe)
    port_detail = port if port else "port not set"
    if probe.get("ok"):
        auto_detected_summary = (
            f"Auto-detected and verified on <strong>{port_detail}</strong> "
            f"with radio <strong>{probe.get('radio_id', 'UNKNOWN')}</strong> "
            f"(profile <strong>{model}</strong>)."
        )
        _status_chip(
            icon,
            label,
            "",
            "good",
            tooltip_rows=[
                auto_detected_summary,
            ],
        )
        st.session_state.connection_freeze_polling = True
    elif port and ((not ports) or (port in ports)):
        _status_chip(icon, label, f"{port_detail} · awaiting radio", "warn")
    else:
        _status_chip(icon, label, port_detail, "bad")
    if probe.get("error") and not probe.get("ok"):
        st.caption(f"Last probe: {probe['error']}")

    ready_now = bool(probe.get("ok") and port and ((not ports) or (port in ports)))
    last_ready = st.session_state.connection_last_ready
    if last_ready is None:
        st.session_state.connection_last_ready = ready_now
        desired_show_controls = not ready_now
        if st.session_state.connection_show_controls != desired_show_controls:
            st.session_state.connection_show_controls = desired_show_controls
            st.rerun()
    elif bool(last_ready) != ready_now:
        st.session_state.connection_last_ready = ready_now
        st.session_state.connection_show_controls = not ready_now
        st.rerun()

    return probe


def tab_boot_logo_flasher():
    """Boot logo flashing via serial connection."""
    if "processed_bmp" not in st.session_state:
        st.session_state.processed_bmp = None
    ports = list_serial_ports()

    bmp_bytes = st.session_state.processed_bmp
    top_left, top_right = st.columns([1, 1])

    with top_left:
        header_cols = st.columns([2.2, 1.2])
        with header_cols[0]:
            st.markdown("#### Step 1 · Connection")
        with header_cols[1]:
            st.session_state.connection_show_controls = st.toggle(
                "Show controls",
                value=st.session_state.connection_show_controls,
                key="connection_show_controls_toggle",
                help="Show model/port selectors.",
            )

        models = list(SERIAL_FLASH_CONFIGS.keys())
        selected_model = st.session_state.selected_model if st.session_state.selected_model in models else models[0]
        st.session_state.selected_model = selected_model
        if st.session_state.selected_port is None and ports:
            st.session_state.selected_port = ports[0]

        model = st.session_state.selected_model
        port = st.session_state.selected_port or "/dev/cu.Plser"
        config = dict(SERIAL_FLASH_CONFIGS[model])
        probe = st.session_state.connection_probe
        ready_now = bool(
            probe.get("ok")
            and probe.get("model") == model
            and probe.get("port") == port
            and port
            and ((not ports) or (port in ports))
        )

        show_controls = st.session_state.connection_show_controls or not ready_now
        if show_controls:
            conn_cols = st.columns(2)
            with conn_cols[0]:
                model = st.selectbox(
                    "Radio Model",
                    models,
                    index=models.index(st.session_state.selected_model),
                    key="model_select",
                )
            with conn_cols[1]:
                if ports:
                    port_options = list(ports) + ["[Enter manually]"]
                    default = st.session_state.selected_port if st.session_state.selected_port in ports else port_options[0]
                    selected = st.selectbox("Serial Port", port_options, index=port_options.index(default), key="port_select")
                    if selected == "[Enter manually]":
                        port = st.text_input("Port Path", value=st.session_state.selected_port or "/dev/cu.Plser")
                    else:
                        port = selected
                else:
                    port = st.text_input("Port Path", value=st.session_state.selected_port or "/dev/cu.Plser")

            st.session_state.selected_model = model
            st.session_state.selected_port = port
        else:
            model = st.session_state.selected_model
            port = st.session_state.selected_port or "/dev/cu.Plser"

        config = dict(SERIAL_FLASH_CONFIGS[model])
        probe = _render_connection_health(model=model, config=config, port=port, ports=ports)
        ready_now = bool(probe.get("ok") and port and ((not ports) or (port in ports)))
        if ready_now:
            st.session_state.connection_show_controls = False
        if not ready_now:
            st.session_state.connection_show_controls = True
        if show_controls != st.session_state.connection_show_controls:
            st.rerun()

    with top_right:
        step2_header_cols = st.columns([2.0, 1.4])
        with step2_header_cols[0]:
            st.markdown("#### Step 2 · Logo")
        with step2_header_cols[1]:
            logo_action_mode = st.toggle(
                "Backup mode",
                value=st.session_state.get("logo_action_backup_mode", False),
                key="logo_action_backup_mode",
                help="Off = flash a new logo, On = backup/download current logo",
            )
        if not logo_action_mode:
            uploaded_file = st.file_uploader(
                "Logo image",
                type=["bmp", "png", "jpg", "jpeg", "gif", "webp", "tiff"],
                key="boot_logo_image",
                label_visibility="collapsed",
                help=(
                    f"Auto-converted to {config['size'][0]}×{config['size'][1]} BMP. "
                    f"Max {BOOT_IMAGE_MAX_UPLOAD_MB} MB."
                ),
            )
            if uploaded_file:
                try:
                    file_size = getattr(uploaded_file, "size", None)
                    if file_size is not None and file_size > BOOT_IMAGE_MAX_UPLOAD_BYTES:
                        st.error(
                            f"Image is too large ({file_size / (1024 * 1024):.1f} MB). "
                            f"Maximum is {BOOT_IMAGE_MAX_UPLOAD_MB} MB."
                        )
                        st.session_state.processed_bmp = None
                        bmp_bytes = None
                    else:
                        original_img = Image.open(uploaded_file)
                        expected_size = config["size"]
                        st.caption(f"Input: {original_img.size[0]}×{original_img.size[1]} ({original_img.format or 'Unknown'})")

                        # Fixed conversion path: auto-convert every upload to target BMP size.
                        processed_img = _process_image_for_radio(
                            original_img,
                            expected_size,
                            "Fill (stretch)",
                            "#000000",
                        )
                        st.session_state.processed_bmp = _image_to_bmp_bytes(processed_img)
                        bmp_bytes = st.session_state.processed_bmp
                        st.success(f"Converted to {expected_size[0]}×{expected_size[1]} BMP and ready to flash.")

                        st.download_button(
                            "💾 Download Processed BMP",
                            data=bmp_bytes,
                            file_name="boot_logo_processed.bmp",
                            mime="image/bmp",
                            use_container_width=True,
                        )
                except Exception as exc:
                    st.error(f"Image processing error: {exc}")
                    bmp_bytes = None
        else:
            backup_supported = all(k in config for k in ("start_addr", "magic")) and config.get("protocol") != "a5_logo"
            if backup_supported:
                backup_simulate = st.toggle("Simulate backup", value=True, key="backup_simulate")
                if st.button("⬇️ Download Current Logo", use_container_width=True):
                    _do_download_logo(port, config, backup_simulate)
            else:
                st.info(
                    "Direct radio logo read-back is not implemented for UV-5RM/UV-17 A5 in this app."
                )
                last_backup = _last_flash_backup_path(model)
                if last_backup.exists():
                    st.download_button(
                        "💾 Download Last Flashed Logo",
                        data=last_backup.read_bytes(),
                        file_name=f"{model.replace(' ', '_').lower()}_last_flashed.bmp",
                        mime="image/bmp",
                        use_container_width=True,
                    )

    st.divider()
    payload_bytes = config["size"][0] * config["size"][1] * 2
    row_cols = st.columns([1.45, 1.05, 1.05, 3.5])
    with row_cols[0]:
        st.markdown(
            "<div style='padding-top:0.44rem;font-size:2rem;font-weight:700;line-height:1.15;'>Step 3 · Flash</div>",
            unsafe_allow_html=True,
        )
    with row_cols[1]:
        st.markdown("<div style='padding-top:0.20rem;'></div>", unsafe_allow_html=True)
        write_mode_enabled = st.toggle(
            "Write mode",
            value=st.session_state.get("step3_write_mode", False),
            key="step3_write_mode",
            help="Off = simulation, On = real flash",
        )
    with row_cols[2]:
        st.markdown("<div style='padding-top:0.20rem;'></div>", unsafe_allow_html=True)
        debug_bytes = st.toggle(
            "Debug bytes",
            value=st.session_state.get("step3_debug_bytes", False),
            key="step3_debug_bytes",
            help="Dump payload/frame artifacts to out/streamlit_logo_debug.",
        )
    with row_cols[3]:
        _step3_mode_badge(
            model=model,
            payload_bytes=payload_bytes,
            addr_mode=config.get("write_addr_mode", "byte"),
            write_mode=write_mode_enabled,
            debug_mode=debug_bytes,
        )

    simulate = not write_mode_enabled
    write_confirmed = True

    can_flash = bool((not logo_action_mode) and bmp_bytes and port)
    with st.form("flash_logo_form", clear_on_submit=False):
        submitted = st.form_submit_button(
            "🚀 Connect & Flash Logo" if write_mode_enabled else "🧪 Simulate Flash",
            type="primary",
            use_container_width=True,
            disabled=not can_flash,
        )
    if submitted:
        if not bmp_bytes:
            st.error("❌ Please upload a BMP file")
        elif not port:
            st.error("❌ Please enter a serial port")
        elif logo_action_mode:
            st.error("❌ Backup mode is enabled. Turn off Backup mode to flash.")
        else:
            _do_flash(
                port,
                bmp_bytes,
                config,
                simulate,
                write_confirmed,
                model,
                debug_bytes=debug_bytes,
            )


def _do_flash(
    port: str,
    bmp_bytes: bytes,
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
            tmp.write(bmp_bytes)
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
            backup_path = _save_last_flash_backup(model, bmp_bytes)
            st.caption(f"Saved last flashed logo backup: {backup_path}")
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
        summary_cols = st.columns(3)
        with summary_cols[0]:
            st.metric("Image Size", f"{config['size'][0]}x{config['size'][1]}")
        with summary_cols[1]:
            st.metric("Payload Bytes", f"{config['size'][0] * config['size'][1] * 2:,}")
        with summary_cols[2]:
            st.metric("Write Mode", config.get("write_addr_mode", "byte"))

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
        logger.exception("Boot logo flash error")
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
                **Recommended path**

                If direct write is unavailable for your specific firmware/build:

                1. Use Step 2 to prepare a compatible BMP
                2. Keep Step 3 in simulation mode for dry runs
                3. Retry with stable cable/power and correct model profile
                """
            )
    finally:
        if bmp_path:
            Path(bmp_path).unlink(missing_ok=True)
        # Resume connection polling after an operation completes.
        st.session_state.connection_freeze_polling = False
        st.session_state.connection_poll_meta["last_probe_ts"] = 0.0


def _do_download_logo(port: str, config: dict, simulate: bool):
    """Execute the download/backup logo operation."""
    try:
        if config.get("protocol") == "a5_logo":
            raise ValueError(
                "Backup logo download is not implemented for A5 serial protocol models in this app."
            )
        required = ("start_addr", "magic")
        missing = [k for k in required if k not in config]
        if missing:
            raise ValueError(
                "Backup logo not supported for this model config "
                f"(missing: {', '.join(missing)})."
            )

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


if __name__ == "__main__":
    main()
