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
import html
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import serial.tools.list_ports
except Exception:
    serial = None

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

from baofeng_logo_flasher.boot_logo import (
    SERIAL_FLASH_CONFIGS,
    list_serial_ports,
    read_radio_id,
)

# Import from core module for unified safety and parsing
from baofeng_logo_flasher.core.safety import (
    WritePermissionError,
    create_streamlit_safety_context,
)
from baofeng_logo_flasher.core.messages import (
    result_to_warnings,
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
    init_write_mode_state,
)

logger = logging.getLogger(__name__)

BOOT_IMAGE_MAX_UPLOAD_MB = 10
BOOT_IMAGE_MAX_UPLOAD_BYTES = BOOT_IMAGE_MAX_UPLOAD_MB * 1024 * 1024
AUTO_PROBE_PORT_LIMIT = 3
AUTO_PROBE_TIMEOUT_SEC = 0.8
PORT_SCAN_TIMEOUT_SEC = 1.0

# Explicit medium-confidence criteria:
# 1) Known USB-UART bridge VID (CP210x/CH34x/PL2303/FTDI), or
# 2) Descriptor/manufacturer/product contains baofeng/serial/uart.
KNOWN_BRIDGE_VIDS = {0x10C4, 0x1A86, 0x067B, 0x0403}
MEDIUM_HINT_TOKENS = ("baofeng", "serial", "uart", "pl2303", "cp210", "ch340", "ftdi")


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
    if "connection_autoselect_reason" not in st.session_state:
        st.session_state.connection_autoselect_reason = ""
    if "connection_scan_seq" not in st.session_state:
        st.session_state.connection_scan_seq = 0
    if "connection_autoselect_seq" not in st.session_state:
        st.session_state.connection_autoselect_seq = 0
    if "connection_last_ports_snapshot" not in st.session_state:
        st.session_state.connection_last_ports_snapshot = ()
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
            overflow-x: hidden;
        }
        [data-testid="stAppViewContainer"] > .main > div {
            padding-top: 1.35rem;
        }
        section.main > div.block-container {
            max-width: 980px;
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
            margin: 0.25rem 0 0.9rem 0;
            width: 100%;
            max-width: none;
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
            display: inline-flex;
            align-items: center;
            vertical-align: middle;
        }
        .conn-chip-info {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 18px;
            height: 18px;
            margin-left: 6px;
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
            right: 0;
            left: auto;
            top: calc(100% + 9px);
            z-index: 20;
            width: min(340px, calc(100vw - 32px));
            min-width: 0;
            max-width: min(340px, calc(100vw - 32px));
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
            text-align: center;
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

def _capability_safety_label(level: SafetyLevel) -> str:
    """Normalize safety text for capability table rows."""
    mapping = {
        SafetyLevel.SAFE: "Safe",
        SafetyLevel.MODERATE: "Moderate",
        SafetyLevel.RISKY: "Risky",
    }
    return mapping.get(level, str(level.value).title())


def _build_model_capability_snapshot(model_name: str) -> dict:
    """Build a unified capabilities snapshot for one model."""
    config = registry_get_model(model_name)
    caps = registry_get_capabilities(model_name)

    ready_ops = sum(1 for c in caps.capabilities if c.supported)
    total_ops = len(caps.capabilities)
    risky_ops = sum(1 for c in caps.capabilities if c.safety == SafetyLevel.RISKY)
    moderate_ops = sum(1 for c in caps.capabilities if c.safety == SafetyLevel.MODERATE)
    logo_mapped = bool(caps.discovered_regions)
    primary_region = caps.discovered_regions[0] if caps.discovered_regions else None

    protocol = config.protocol.value.upper() if config else "Unknown"
    baud = str(config.baud_rate) if config else "Unknown"
    region_text = (
        f"0x{primary_region.start_addr:04X} ({primary_region.width}x{primary_region.height})"
        if primary_region
        else "Unmapped"
    )

    return {
        "model": model_name,
        "protocol": protocol,
        "baud": baud,
        "logo_mapped": logo_mapped,
        "logo_region": region_text,
        "ready_ops": ready_ops,
        "total_ops": total_ops,
        "risky_ops": risky_ops,
        "moderate_ops": moderate_ops,
        "caps": caps,
    }


def tab_capabilities():
    """Show capabilities report for radio models."""
    import json

    _render_section_header(
        "Model Capabilities",
        [
            "Registry-driven and refreshed from current model definitions.",
            "Use compact view by default; expand details only when needed.",
        ],
        "Capabilities help",
    )

    controls_left, controls_mid, controls_right = st.columns([2.4, 1.0, 1.0], vertical_alignment="center")
    with controls_left:
        models = registry_list_models()
        selected_model = st.selectbox(
            "Model",
            models,
            index=models.index("UV-5RM") if "UV-5RM" in models else 0,
            label_visibility="collapsed",
        )
    with controls_mid:
        show_details = st.toggle("Show details", value=False, key="caps_show_details")
    with controls_right:
        export_json = st.toggle("Show JSON", value=False, key="caps_show_json")

    snapshot = _build_model_capability_snapshot(selected_model)
    caps = snapshot["caps"]
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if export_json:
        st.json(caps.to_dict())
        return

    summary_items = [
        ("Model", snapshot["model"]),
        ("Protocol", snapshot["protocol"]),
        ("Baud", snapshot["baud"]),
        ("Logo", "Mapped" if snapshot["logo_mapped"] else "Unmapped"),
        ("Ops", f"{snapshot['ready_ops']}/{snapshot['total_ops']} ready"),
    ]
    if snapshot["risky_ops"] > 0:
        summary_items.append(("Risky", str(snapshot["risky_ops"])))

    summary_html = "".join(
        (
            "<span style='display:inline-flex;align-items:center;gap:0.35rem;"
            "padding:0.33rem 0.52rem;border-radius:999px;border:1px solid rgba(255,255,255,0.12);"
            "background:rgba(255,255,255,0.03);font-size:0.86rem;white-space:nowrap;'>"
            f"<span style='opacity:0.75'>{html.escape(k)}:</span>"
            f"<span style='font-weight:700'>{html.escape(v)}</span></span>"
        )
        for k, v in summary_items
    )
    st.markdown(
        (
            "<div style='display:flex;flex-wrap:wrap;gap:0.42rem;"
            "margin:0.22rem 0 0.52rem 0;'>"
            f"{summary_html}</div>"
        ),
        unsafe_allow_html=True,
    )
    st.caption(f"Snapshot: {generated_at} (local registry data)")

    cap_rows = []
    for cap_info in caps.capabilities:
        cap_rows.append({
            "Operation": cap_info.capability.name.replace("_", " ").title(),
            "Status": "Ready" if cap_info.supported else "Blocked",
            "Safety": _capability_safety_label(cap_info.safety),
            "Detail": cap_info.reason,
        })

    ops_height = min(46 + (len(cap_rows) * 35), 320)
    st.dataframe(cap_rows, use_container_width=True, hide_index=True, height=ops_height)

    if show_details:
        with st.expander("Details", expanded=True):
            if caps.discovered_regions:
                region_rows = []
                for region in caps.discovered_regions:
                    region_rows.append({
                        "Address": f"0x{region.start_addr:04X}-0x{region.end_addr:04X}",
                        "Dimensions": f"{region.width}x{region.height}",
                        "Color": region.color_mode,
                        "Encrypted": "Yes" if region.encrypt else "No",
                        "Bytes": f"{region.length:,}",
                    })
                regions_height = min(46 + (len(region_rows) * 35), 220)
                st.dataframe(region_rows, use_container_width=True, hide_index=True, height=regions_height)
            else:
                st.info("Logo region not mapped for this model.")

            if caps.notes:
                notes_html = "<br/>".join(f"• {html.escape(note)}" for note in caps.notes)
                st.markdown(
                    (
                        "<div style='margin-top:0.2rem;padding:0.58rem 0.66rem;border-radius:10px;"
                        "border:1px solid rgba(255,255,255,0.10);background:rgba(255,255,255,0.02);"
                        "font-size:0.9rem;line-height:1.35;'>"
                        f"{notes_html}</div>"
                    ),
                    unsafe_allow_html=True,
                )

    with st.expander("All Registered Models", expanded=False):
        model_rows = []
        for model_name in registry_list_models():
            row = _build_model_capability_snapshot(model_name)
            model_rows.append({
                "Model": row["model"],
                "Protocol": row["protocol"],
                "Baud": row["baud"],
                "Logo": "Mapped" if row["logo_mapped"] else "Unmapped",
                "Ready Ops": f"{row['ready_ops']}/{row['total_ops']}",
                "Risky Ops": row["risky_ops"],
                "Moderate Ops": row["moderate_ops"],
            })
        model_rows.sort(key=lambda r: r["Model"])
        all_height = min(46 + (len(model_rows) * 35), 320)
        st.dataframe(model_rows, use_container_width=True, hide_index=True, height=all_height)


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


def _safe_text(value: object) -> str:
    """Normalize optional device fields to lowercase text."""
    if value is None:
        return ""
    return str(value).strip().lower()


def _list_port_metadata() -> dict:
    """Return metadata for visible ports keyed by device path."""
    if serial is None:
        return {}

    info = {}
    for p in serial.tools.list_ports.comports():
        info[p.device] = {
            "device": p.device,
            "description": _safe_text(getattr(p, "description", "")),
            "manufacturer": _safe_text(getattr(p, "manufacturer", "")),
            "product": _safe_text(getattr(p, "product", "")),
            "hwid": _safe_text(getattr(p, "hwid", "")),
            "vid": getattr(p, "vid", None),
            "pid": getattr(p, "pid", None),
        }
    return info


def _medium_confidence_score(port_info: dict) -> int:
    """
    Score medium-confidence signals for a serial port.

    This intentionally excludes active probing. It is used only as a fallback
    when handshake confidence is unavailable.
    """
    score = 0

    vid = port_info.get("vid")
    if isinstance(vid, int) and vid in KNOWN_BRIDGE_VIDS:
        score += 2

    desc_blob = " ".join(
        [
            port_info.get("description", ""),
            port_info.get("manufacturer", ""),
            port_info.get("product", ""),
            port_info.get("hwid", ""),
        ]
    )
    if any(token in desc_blob for token in MEDIUM_HINT_TOKENS):
        score += 1

    return score


def _probe_radio_identity(
    port: str,
    model: str,
    config: dict,
    timeout_cap: float,
) -> dict:
    """
    Perform a non-destructive identity probe for ranking.

    This uses read-only handshake/ident operations only.
    """
    protocol = "uv17pro" if config.get("protocol") == "a5_logo" else "uv5r"
    try:
        radio_id = read_radio_id(
            port,
            magic=config.get("magic"),
            baudrate=int(config.get("baudrate", 115200)),
            timeout=min(float(config.get("timeout", 2.0)), timeout_cap),
            protocol=protocol,
        )
        return {
            "port": port,
            "model": model,
            "ok": True,
            "radio_id": radio_id,
            "error": "",
        }
    except Exception as exc:
        # Handshake failure is treated as low/unknown confidence.
        return {
            "port": port,
            "model": model,
            "ok": False,
            "radio_id": "",
            "error": str(exc),
        }


def _rank_ports_for_autoselect(ports: list[str], metadata: dict) -> list[str]:
    """Rank ports by medium-confidence score and stable device-name fallback."""
    return sorted(
        ports,
        key=lambda dev: (
            _medium_confidence_score(metadata.get(dev, {"device": dev})),
            dev.lower(),
        ),
        reverse=True,
    )


def _auto_select_port(
    *,
    model: str,
    config: dict,
    ports: list[str],
    force_full_scan: bool,
) -> tuple[Optional[str], str]:
    """
    Auto-select a likely port using bounded probing and explicit fallback rules.

    Selection precedence:
    1) High confidence: exactly one successful handshake probe.
    2) Medium confidence: no high confidence, and exactly one strongest
       descriptor/VID-based candidate.
    """
    if not ports:
        return None, "No serial ports detected."

    metadata = _list_port_metadata()
    ranked_ports = _rank_ports_for_autoselect(ports, metadata)

    probe_limit = len(ranked_ports) if force_full_scan else min(AUTO_PROBE_PORT_LIMIT, len(ranked_ports))
    probed = ranked_ports[:probe_limit]
    handshake_hits = []
    handshake_failed = set()
    timeout_cap = PORT_SCAN_TIMEOUT_SEC if force_full_scan else AUTO_PROBE_TIMEOUT_SEC

    for dev in probed:
        probe = _probe_radio_identity(dev, model, config, timeout_cap=timeout_cap)
        if probe.get("ok"):
            handshake_hits.append(dev)
        else:
            handshake_failed.add(dev)
            logger.info("Auto-probe handshake failed on %s: %s", dev, probe.get("error", "unknown"))

    if len(handshake_hits) == 1:
        return handshake_hits[0], f"Auto-selected by successful handshake on {handshake_hits[0]}."

    if len(handshake_hits) > 1:
        return None, "Multiple radios responded; select port manually."

    medium_ranked = []
    for dev in ranked_ports:
        if dev in handshake_failed:
            continue
        info = metadata.get(dev, {"device": dev})
        score = _medium_confidence_score(info)
        medium_ranked.append((dev, score))
    medium_ranked = [item for item in medium_ranked if item[1] > 0]
    medium_ranked.sort(key=lambda item: (item[1], item[0].lower()), reverse=True)

    if len(medium_ranked) == 1:
        dev, score = medium_ranked[0]
        return dev, f"Auto-selected medium-confidence port ({dev}, score={score})."

    if len(medium_ranked) >= 2 and medium_ranked[0][1] > medium_ranked[1][1]:
        dev, score = medium_ranked[0]
        return dev, f"Auto-selected strongest medium-confidence port ({dev}, score={score})."

    limit_note = f"Auto-probe limit {AUTO_PROBE_PORT_LIMIT} reached." if not force_full_scan else "Full scan completed."
    return None, f"{limit_note} No unique high-confidence candidate."


def _probe_connection_status(port: str, model: str, config: dict, force: bool = False) -> dict:
    """Probe radio availability and cache short-lived status in session state."""
    now = time.time()
    cache = st.session_state.connection_probe
    same_target = cache.get("port") == port and cache.get("model") == model
    fresh = now - float(cache.get("ts", 0)) < 5.0
    if not force and same_target and fresh:
        return cache

    probe = _probe_radio_identity(port, model, config, timeout_cap=1.5)
    cache = {
        "port": port,
        "model": model,
        "ts": now,
        "ok": bool(probe.get("ok")),
        "radio_id": probe.get("radio_id", ""),
        "error": probe.get("error", ""),
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


def _tooltip_icon_html(tooltip_rows: list[str], aria_label: str = "Details") -> str:
    """Render a unified Step 1-style tooltip icon."""
    rows = [
        html.escape(str(row))
        for row in tooltip_rows
        if row is not None and str(row).strip()
    ]
    if not rows:
        return ""
    rows_html = "<br/>".join(rows)
    return (
        "<span class='conn-chip'>"
        f"<span class='conn-chip-info' aria-label='{html.escape(aria_label)}'>i"
        f"<span class='conn-chip-tip'>{rows_html}</span>"
        "</span></span>"
    )


def _render_inline_toggle(
    label: str,
    tooltip_rows: list[str],
    *,
    key: str,
    value: bool,
    aria_label: str,
    control_nudge_top: str = "0rem",
    text_nudge_top: str = "0rem",
) -> bool:
    """Render a toggle + label + tooltip on a single row."""
    toggle_col, text_col = st.columns([0.95, 6.05], gap="small", vertical_alignment="center")
    with toggle_col:
        if control_nudge_top != "0rem":
            st.markdown(f"<div style='margin-top:{control_nudge_top};'></div>", unsafe_allow_html=True)
        enabled = st.toggle(label, value=value, key=key, label_visibility="collapsed")
    with text_col:
        st.markdown(
            (
                "<div style='display:inline-flex;align-items:center;font-weight:600;line-height:1.15;"
                f"margin-left:0.24rem;padding-top:{text_nudge_top};white-space:nowrap;'>"
                f"{html.escape(label)}{_tooltip_icon_html(tooltip_rows, aria_label)}"
                "</div>"
            ),
            unsafe_allow_html=True,
        )
    return enabled


def _render_section_header(title: str, tooltip_rows: Optional[list[str]] = None, aria_label: str = "Section help") -> None:
    """Render a section header with optional aligned tooltip icon."""
    tooltip_html = _tooltip_icon_html(tooltip_rows or [], aria_label) if tooltip_rows else ""
    st.markdown(
        (
            "<div style='display:inline-flex;align-items:center;"
            "font-size:2rem;font-weight:700;line-height:1.15;'>"
            f"{html.escape(title)}{tooltip_html}"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


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
    tooltip_html = _tooltip_icon_html(tooltip_rows or [], aria_label="Connection details")
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
            f"<div style='padding-top:0.02rem;text-align:right;'>"
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
    ports_snapshot = tuple(sorted(ports))

    bmp_bytes = st.session_state.processed_bmp
    top_left, top_right = st.columns([1, 1])

    with top_left:
        header_cols = st.columns([2.2, 0.9, 0.9], vertical_alignment="center")
        with header_cols[0]:
            _render_section_header("Step 1 · Connection")
        with header_cols[1]:
            st.session_state.connection_show_controls = _render_inline_toggle(
                "Show controls",
                ["Show or hide model and port selectors."],
                key="connection_show_controls_toggle",
                value=st.session_state.connection_show_controls,
                aria_label="Show controls help",
            )
        with header_cols[2]:
            if st.button("Scan", use_container_width=True):
                st.session_state.connection_scan_seq += 1

        models = list(SERIAL_FLASH_CONFIGS.keys())
        selected_model = st.session_state.selected_model if st.session_state.selected_model in models else models[0]
        st.session_state.selected_model = selected_model
        should_autoselect = (
            ports_snapshot != st.session_state.connection_last_ports_snapshot
            or st.session_state.connection_autoselect_seq != st.session_state.connection_scan_seq
            or (st.session_state.selected_port and st.session_state.selected_port not in ports)
            or (not st.session_state.selected_port)
        )

        if should_autoselect:
            force_scan = st.session_state.connection_autoselect_seq != st.session_state.connection_scan_seq
            auto_port, reason = _auto_select_port(
                model=selected_model,
                config=dict(SERIAL_FLASH_CONFIGS[selected_model]),
                ports=ports,
                force_full_scan=force_scan,
            )
            st.session_state.connection_last_ports_snapshot = ports_snapshot
            st.session_state.connection_autoselect_seq = st.session_state.connection_scan_seq
            st.session_state.connection_autoselect_reason = reason
            if auto_port:
                st.session_state.selected_port = auto_port
            elif st.session_state.selected_port not in ports:
                st.session_state.selected_port = None

        model = st.session_state.selected_model
        port = st.session_state.selected_port or ""
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
                        port = st.text_input("Port Path", value=st.session_state.selected_port or "")
                    else:
                        port = selected
                else:
                    port = st.text_input("Port Path", value=st.session_state.selected_port or "")

            st.session_state.selected_model = model
            st.session_state.selected_port = port
        else:
            model = st.session_state.selected_model
            port = st.session_state.selected_port or ""

        st.caption(
            "Auto-detect signals: handshake=high, known USB-UART VID/descriptor=medium. "
            f"Auto-probe max {AUTO_PROBE_PORT_LIMIT} ports unless you click Scan. "
            f"{st.session_state.connection_autoselect_reason}"
        )

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
        step2_tip_rows = [
            f"Auto-converted to {config['size'][0]}×{config['size'][1]} BMP.",
            f"Max {BOOT_IMAGE_MAX_UPLOAD_MB} MB.",
        ]
        _render_section_header("Step 2 · Logo", step2_tip_rows, "Step 2 upload help")
        uploaded_file = st.file_uploader(
            "Logo image",
            type=["bmp", "png", "jpg", "jpeg", "gif", "webp", "tiff"],
            key="boot_logo_image",
            label_visibility="collapsed",
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

    st.divider()
    payload_bytes = config["size"][0] * config["size"][1] * 2
    row_cols = st.columns([1.45, 1.2, 1.2, 3.2], vertical_alignment="center")
    with row_cols[0]:
        _render_section_header("Step 3 · Flash")
    with row_cols[1]:
        write_mode_enabled = _render_inline_toggle(
            "Write mode",
            ["Off: simulation mode.", "On: real flash write."],
            key="step3_write_mode",
            value=st.session_state.get("step3_write_mode", False),
            aria_label="Write mode help",
            control_nudge_top="-0.24rem",
            text_nudge_top="-0.04rem",
        )
    with row_cols[2]:
        debug_bytes = _render_inline_toggle(
            "Debug bytes",
            ["Dump payload/frame artifacts to out/streamlit_logo_debug."],
            key="step3_debug_bytes",
            value=st.session_state.get("step3_debug_bytes", False),
            aria_label="Debug bytes help",
            control_nudge_top="-0.24rem",
            text_nudge_top="-0.04rem",
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

    can_flash = bool(bmp_bytes and port)
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

        # Hide progress UI once operation has finished.
        progress_placeholder.empty()
        status_placeholder.empty()

        # Success output
        if not result.ok:
            raise Exception("\n".join(result.errors))

        backup_path = None
        if simulate or result.metadata.get("simulated"):
            result_msg = result.metadata.get("result_message", "Simulation complete")
            st.info(f"✓ **Simulation complete:**\n{result_msg}")
            st.success("Ready for real flashing when you are!")
        else:
            result_msg = result.metadata.get("result_message", "Flash successful!")
            backup_path = _save_last_flash_backup(model, bmp_bytes)
            payload_bytes = config["size"][0] * config["size"][1] * 2
            backup_hint = f"Last backup: {backup_path}"
            tooltip_rows = [
                f"Image {config['size'][0]}x{config['size'][1]} · Write mode {config.get('write_addr_mode', 'byte')}",
                f"Payload bytes: {payload_bytes:,}",
                backup_hint,
                "If logo does not appear, power cycle the radio.",
            ]
            detail_icon_html = _tooltip_icon_html(tooltip_rows, aria_label="Flash details")
            st.markdown(
                (
                    "<div style='padding:0.95rem 1rem; border-radius:0.75rem; "
                    "border:1px solid rgba(70, 231, 165, 0.25); "
                    "background:linear-gradient(90deg, rgba(28,129,95,0.26), rgba(28,129,95,0.12));'>"
                    f"<div style='font-weight:700;'>✅ Flash successful! {result_msg} {detail_icon_html}</div>"
                    "</div>"
                ),
                unsafe_allow_html=True,
            )

        if debug_bytes:
            st.caption("Debug artifacts: out/streamlit_logo_debug")

        # Show any warnings from the operation
        if result.warnings:
            structured_warnings = result_to_warnings(result)
            render_warning_list(structured_warnings, collapsed_default=True)

        if result.logs:
            with st.expander("📜 Raw Logs", expanded=False):
                st.code("\n".join(result.logs), language="text")

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


if __name__ == "__main__":
    main()
