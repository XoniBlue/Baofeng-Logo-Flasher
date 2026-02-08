# Development Guide

Implementation guide for contributors. For end-user setup, see `README.md`.

## Doc Map

- Product usage: `README.md`
- Protocol specifics: `LOGO_PROTOCOL.md`
- Runtime issues: `TROUBLESHOOTING.md`
- UI details: `docs/UI_BEHAVIOR.md`
- Clone layout notes: `docs/IMAGE_LAYOUT.md`

## Runtime Entry Points

- CLI: `src/baofeng_logo_flasher/cli.py`
- UI: `src/baofeng_logo_flasher/streamlit_ui.py`
- Package metadata/scripts: `pyproject.toml`

## Architecture

### Protocol Layer

Files:
- `src/baofeng_logo_flasher/protocol/uv5rm_transport.py`
- `src/baofeng_logo_flasher/protocol/uv5rm_protocol.py`
- `src/baofeng_logo_flasher/protocol/logo_protocol.py`

Responsibilities:
- serial transport
- clone identify/read/write protocol
- A5 logo framing, CRC, chunking, payload conversion

### Boot Logo Layer

File:
- `src/baofeng_logo_flasher/boot_logo.py`

Responsibilities:
- `SERIAL_FLASH_CONFIGS`
- route between legacy/clone path and A5 path
- model-specific write addressing behavior

Critical behavior:
- UV-5RM/UV-17 family use `write_addr_mode: "chunk"`.

### Core Actions and Safety

Files:
- `src/baofeng_logo_flasher/core/actions.py`
- `src/baofeng_logo_flasher/core/safety.py`
- `src/baofeng_logo_flasher/core/parsing.py`

Responsibilities:
- shared CLI/UI workflows
- write permission contract
- simulation behavior

### Image and Patch Utilities

Files:
- `src/baofeng_logo_flasher/logo_codec.py`
- `src/baofeng_logo_flasher/logo_patcher.py`
- `src/baofeng_logo_flasher/bitmap_scanner.py`

Responsibilities:
- clone bitmap format handling
- offline patching
- candidate bitmap discovery

### Model Registry

File:
- `src/baofeng_logo_flasher/models/registry.py`

Responsibilities:
- model metadata
- capabilities and safety hints

## Command Paths

### Direct A5 Flash Path

- CLI command: `upload-logo-serial`
- shared action: `core.actions.flash_logo_serial`
- protocol implementation: `protocol.logo_protocol`

### Clone Patch Path

- commands: `patch-logo`, `flash-logo`, `upload-logo`, `download-logo`
- protocol modules: `uv5rm_protocol`, `uv5rm_transport`

## Safety Contract

Real writes require:
- `--write`
- `WRITE` confirmation token

Simulation/dry paths must not write to radio.

## Debug and Byte-True Tooling

- `--debug-bytes --debug-dir ...` on `upload-logo-serial`
- `tools/logo_payload_tools.py`
- `tools/generate_logo_probes.py`

## Local Development

### Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[ui,dev]"
```

### Test

```bash
pytest tests/ -v
```

## Change Rule

When protocol defaults or command behavior change, update these docs in the same change:
- `README.md`
- `LOGO_PROTOCOL.md`
- `TROUBLESHOOTING.md`
- `DEVELOPMENT.md`
- `docs/UI_BEHAVIOR.md`
