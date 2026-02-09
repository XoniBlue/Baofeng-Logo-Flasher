# UI Behavior and Safety

This document describes current Streamlit behavior for flashing and safety.

## Entry Point

- Module: `src/baofeng_logo_flasher/streamlit_ui.py`
- Launch:
  - `baofeng-logo-flasher-ui`
  - `streamlit run src/baofeng_logo_flasher/streamlit_ui.py`

## Tabs

- `Boot Logo Flasher`
- `Capabilities`

## Boot Logo Flasher Flow

1. Step 1: connection detection (model/port controls + live status)
2. Step 2: upload and auto-convert image to model BMP size
3. Step 3: select simulation/write mode and optional debug bytes
4. Execute `core.actions.flash_logo_serial`
5. Show progress, result, warnings, logs

## Address Mode Behavior

The flasher uses model config from `SERIAL_FLASH_CONFIGS`.
For UV-5RM/UV-17-family, effective A5 write mode is:
- `write_addr_mode: chunk`

This was required in older versions or legacy modes to avoid the top-line-only/gray-screen failure.

## Safety Contract

Write is allowed only when:
- write mode is enabled
- operation is not in simulation mode

Enforced by:
- `core/safety.py` (`require_write_permission`)

## Simulation Mode

When simulation is enabled:
- no serial write occurs
- UI still validates workflow and shows status

## Protocol Debug Mode

Boot Logo Flasher includes optional protocol debug bytes dump.
When enabled, artifacts are written to:
- `out/streamlit_logo_debug`

Artifacts include payload/frame binaries and manifest hashes.

## Troubleshooting Note

If UI still behaves like old logic after code updates:
1. fully restart Streamlit process
2. re-run flash with protocol debug enabled
3. inspect `out/streamlit_logo_debug/manifest.json` for active mode/details
