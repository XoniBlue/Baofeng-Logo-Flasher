# UI Behavior and Safety

This document describes current Streamlit safety behavior and confirmation flow.

## UI Entry Point
- Module: `src/baofeng_logo_flasher/streamlit_ui.py`
- Launch command: `baofeng-logo-flasher-ui` or `streamlit run src/baofeng_logo_flasher/streamlit_ui.py`

The UI renders four tabs:
- `Capabilities`
- `Tools & Inspect`
- `Verify & Patch`

Capabilities include:
- Warning display
- Write confirmation controls (when required)

1. Write mode enabled
3. Confirmation token typed as `WRITE`

These rules are enforced by:
- UI widgets in `ui/components.py`
- Core gate `core/safety.py` (`require_write_permission`)

## Simulation Behavior

Boot logo flashing workflows include simulation mode.
- No radio write is attempted
- UI shows simulated result/warnings

## Boot Logo Flasher Tab Behavior

Main flow:
4. Upload and preprocess image (fit/fill/crop)
6. Execute flash flow with progress UI

The tab also contains explicit warnings about model/hardware limitations (for example, external flash access caveats).

## Tools and Patch Tabs

- `Tools & Inspect`: clone metrics, scan candidates, image converter
- `Verify & Patch`: pre-write verification and offline patch utility

These workflows are designed to work without immediate radio write access.

## Developer Guidance

1. Reuse `render_write_confirmation()` and/or `render_safety_panel()`.
2. Use a `SafetyContext` and `require_write_permission()`.
3. Provide simulation mode where practical.
