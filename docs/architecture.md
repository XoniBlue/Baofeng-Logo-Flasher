# Architecture

## Overview

The codebase is split into runtime layers:

1. Entrypoints (console scripts, defined in `pyproject.toml`)
   - CLI: `baofeng_logo_flasher.cli:main`
   - UI: `baofeng_logo_flasher.streamlit_ui:launch`

2. UI layer
   - `src/baofeng_logo_flasher/ui/cli.py`
   - `src/baofeng_logo_flasher/ui/streamlit_ui.py`
   - `src/baofeng_logo_flasher/ui/components.py`

3. Shared core logic (safety, parsing, results, actions)
   - `src/baofeng_logo_flasher/core/safety.py`
   - `src/baofeng_logo_flasher/core/actions.py`
   - `src/baofeng_logo_flasher/core/parsing.py`
   - `src/baofeng_logo_flasher/core/results.py`
   - `src/baofeng_logo_flasher/core/messages.py`

4. Domain services
   - `src/baofeng_logo_flasher/core/boot_logo.py`
   - `src/baofeng_logo_flasher/core/features.py`

5. Protocol/IO layer (timing-sensitive serial logic)
   - `src/baofeng_logo_flasher/protocol/uv5rm_transport.py`
   - `src/baofeng_logo_flasher/protocol/uv5rm_protocol.py`
   - `src/baofeng_logo_flasher/protocol/logo_protocol.py`
   - `src/baofeng_logo_flasher/protocol/dm32uv_picture_protocol.py`

6. Utility helpers (pure helpers, no serial timing)
   - `src/baofeng_logo_flasher/utils/bmp_utils.py`
   - `src/baofeng_logo_flasher/utils/logo_codec.py`
   - `src/baofeng_logo_flasher/utils/crypto.py`
   - `src/baofeng_logo_flasher/utils/firmware_tools.py`
   - `src/baofeng_logo_flasher/utils/firmware_crypto.py`

7. Models/capabilities registry
   - `src/baofeng_logo_flasher/models/registry.py`

## Dependency Diagram (Text)

`UI (CLI/Streamlit)` -> `core/*` + `models/*` -> `core/boot_logo` -> `protocol/*` -> `pyserial`

Additional path:
`UI` -> `utils/*` -> `Pillow` for image preprocessing / encoding.

## Runtime Flow

### CLI

1. Console script resolves to `baofeng_logo_flasher.cli:main`.
2. `ui/cli.py:main` invokes the Typer app (`app()`).
3. Command handler calls into core actions and protocol modules.

### Streamlit UI

1. Console script resolves to `baofeng_logo_flasher.streamlit_ui:launch`.
2. `ui/streamlit_ui.py:launch` bootstraps Streamlit.
3. `ui/streamlit_ui.py:main` initializes state, renders tabs, and delegates to core actions.

### Direct Serial Logo Flash (A5)

CLI (`upload-logo-serial`) and UI converge on shared core action:

1. Build safety context:
   - CLI: `core/safety.py:create_cli_safety_context`
   - UI: `core/safety.py:create_streamlit_safety_context`
2. Enforce write gate:
   - `core/safety.py:require_write_permission`
3. Execute action:
   - `core/actions.py:flash_logo_serial`
   - delegates to `core/boot_logo.py:flash_logo`
   - dispatches into `protocol/logo_protocol.py` for A5 upload

## Safety Gate

All writes must be gated by:
- `core/safety.py:require_write_permission`

UIs must not perform device writes without passing through this gate.

## Notes

Some old import paths are kept as compatibility wrappers (for entry points and older module paths), but new code should import from `ui/`, `core/`, and `utils/` explicitly.

