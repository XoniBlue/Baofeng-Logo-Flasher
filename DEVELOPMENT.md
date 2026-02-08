# Development Guide

This document describes the current architecture and extension points in this workspace.

## Runtime Targets

- CLI entrypoint: `src/baofeng_logo_flasher/cli.py`
- UI entrypoint: `src/baofeng_logo_flasher/streamlit_ui.py`
- Package metadata/scripts: `pyproject.toml`

## Architecture

### 1. Protocol Layer

Files:
- `src/baofeng_logo_flasher/protocol/uv5rm_transport.py`
- `src/baofeng_logo_flasher/protocol/uv5rm_protocol.py`
- `src/baofeng_logo_flasher/protocol/logo_protocol.py`

Responsibilities:
- Serial transport management
- Radio identify/read/write operations
- A5 logo-protocol framing support

### 2. Boot Logo Layer

File:
- `src/baofeng_logo_flasher/boot_logo.py`

Responsibilities:
- Boot logo service abstractions
- Model flash configuration (`SERIAL_FLASH_CONFIGS`)
- Image conversion helpers for radio logo formats
Files:
- `src/baofeng_logo_flasher/core/actions.py`
- `src/baofeng_logo_flasher/core/safety.py`
- `src/baofeng_logo_flasher/core/parsing.py`
Responsibilities:
- Shared operations for CLI/UI

### 4. Image Tools Layer
- `src/baofeng_logo_flasher/logo_patcher.py`
- `src/baofeng_logo_flasher/bitmap_scanner.py`

Responsibilities:

### 5. Model Registry Layer
Responsibilities:
- Model protocol config and capabilities

### 6. UI Components Layer

Responsibilities:
## Safety Contract

Expected checks:
- Explicit write enablement
- Confirmation token handling (`WRITE`)
- Simulation mode bypass for non-destructive runs

- `ports`, `list-devices`, `list-models`, `show-model-config`
- `capabilities`, `detect`
- `inspect-img`, `scan-logo`, `scan-bitmaps`, `patch-logo`, `verify-image`
`streamlit_ui.py` tabs:
- Capabilities
- Tools & Inspect
- Verify & Patch
Global safety panel is rendered from `ui/components.py`.

## Tooling
### Install
```bash
python3 -m venv venv
source venv/bin/activate
```bash
```

### Make Targets

See `Makefile` for:
- `make install`
- `make serve` / `make start` / `make stop`
- `make test`
- `make clean`

## Adding or Changing Features

### Add a new CLI command

1. Add Typer command in `cli.py`.
2. Reuse shared parsers/safety/core actions where possible.
3. Keep destructive operations behind write-gating and confirmation.
4. Add tests under `tests/`.
5. Update `README.md` command list.

### Add or update model behavior

1. Update `models/registry.py`.
2. Update or map serial settings in `boot_logo.py` if needed.
3. Validate through `list-models`, `show-model-config`, and `capabilities`.
4. Update docs with model caveats.

### Add a UI workflow

1. Add UI control in `streamlit_ui.py`.
2. Use `ui/components.py` for safety/confirmation patterns.
3. Use `core.actions` for shared operation logic where possible.

## Known Documentation Rule

If command behavior changes, update these in the same change set:
- `README.md`
- `DEVELOPMENT.md`
- `docs/UI_BEHAVIOR.md`
- `docs/IMAGE_LAYOUT.md` (if discovery/format assumptions change)
- `TROUBLESHOOTING.md` (if connection expectations change)
