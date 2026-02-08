# UI Behavior and Safety

This document describes current Streamlit behavior for flashing, safety, and diagnostics.

## Entry Point

- Module: `src/baofeng_logo_flasher/streamlit_ui.py`
- Launch:
  - `baofeng-logo-flasher-ui`
  - `streamlit run src/baofeng_logo_flasher/streamlit_ui.py`

## Tabs

- `Boot Logo Flasher`
- `Capabilities`
- `Tools & Inspect`
- `Verify & Patch`

## Boot Logo Flasher Flow

1. Select model and serial port
2. Upload image and preprocess (fit/fill/crop)
3. Convert processed image to BMP bytes
4. Confirm write safety
5. Execute `core.actions.flash_logo_serial`
6. Show progress, result, warnings, logs

## Address Mode Behavior

The flasher uses model config from `SERIAL_FLASH_CONFIGS`.
For UV-5RM/UV-17-family, effective A5 write mode is:
- `write_addr_mode: chunk`

This is required to avoid the top-line-only/gray-screen failure.

## Safety Contract

Write is allowed only when:
- write mode is enabled
- user confirmation is provided
- operation is not in simulation mode

Enforced by:
- UI components in `ui/components.py`
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
