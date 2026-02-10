# Baofeng Logo Flasher: Repository Documentation

This `repodocs/` set documents the **actual runtime behavior** of the repository as implemented in code under `src/baofeng_logo_flasher/` and package metadata in `pyproject.toml`.

## What It Is

`baofeng-logo-flasher` is a Python application for:
- serial-port radio detection,
- A5 boot-logo upload workflows,
- and a Streamlit UI focused on direct serial logo flashing.

Primary runtime entrypoints are:
- CLI console script: `baofeng-logo-flasher` → `src/baofeng_logo_flasher/cli.py` (`main`)
- UI console script: `baofeng-logo-flasher-ui` → `src/baofeng_logo_flasher/streamlit_ui.py` (`launch`)

References:
- `pyproject.toml` (`[project.scripts]`)
- `src/baofeng_logo_flasher/cli.py` (`main`, Typer `app` commands)
- `src/baofeng_logo_flasher/streamlit_ui.py` (`launch`, `main`)

## Features

Implemented features in runtime code:
- List serial ports: `cli.py:ports`
- Detect radio identity/version: `cli.py:detect`, `protocol/uv5rm_protocol.py:UV5RMProtocol.identify_radio`
- Upload logo via A5 serial logo protocol: `cli.py:upload_logo_serial`, `core/actions.py:flash_logo_serial`, `protocol/logo_protocol.py:LogoUploader.upload_logo`
- Streamlit guided workflow: `streamlit_ui.py:tab_boot_logo_flasher`, `_do_flash`

Safety enforcement exists in shared core module:
- `core/safety.py:require_write_permission`

## Supported Platforms

Code is cross-platform Python with serial I/O via `pyserial`:
- macOS/Linux/Windows are all technically supported when Python + serial drivers/permissions are available.
- No OS-specific platform guards exist in runtime modules.

References:
- `pyproject.toml` (`requires-python = ">=3.9"`)
- `pyproject.toml` dependencies (`pyserial`, `pillow`, `rich`, `typer`, optional `streamlit`)

## Quickstart

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows PowerShell: .\.venv\Scripts\Activate.ps1
pip install -e ".[ui]"

baofeng-logo-flasher --help
baofeng-logo-flasher-ui
```

If UI extras are missing, `streamlit_ui.py` exits early with an install hint.
Reference: `src/baofeng_logo_flasher/streamlit_ui.py` (top-level guarded import and `sys.exit(1)`).

## Detailed Usage

### CLI: inspect ports and models

```bash
baofeng-logo-flasher ports
baofeng-logo-flasher list-models
baofeng-logo-flasher show-model-config UV-5RM
```

### CLI: direct A5 serial logo upload (recommended for UV-5RM/UV-17 family)

Dry run:

```bash
baofeng-logo-flasher upload-logo-serial \
  --port /dev/ttyUSB0 \
  --in logo.bmp \
  --model UV-5RM \
  --dry-run
```

Real write (requires explicit safety flags):

```bash
baofeng-logo-flasher upload-logo-serial \
  --port /dev/ttyUSB0 \
  --in logo.bmp \
  --model UV-5RM \
  --write --confirm WRITE
```

### UI

```bash
baofeng-logo-flasher-ui
```

UI workflow is implemented in `streamlit_ui.py`:
1. Step 1 connection (`tab_boot_logo_flasher` + `_render_connection_health`)
2. Step 2 image upload/convert (`_process_image_for_radio`, `_image_to_bmp_bytes`)
3. Step 3 simulate or flash (`_do_flash`)

## Configuration

Runtime configuration sources:
- CLI options (Typer command args/options) in `cli.py`
- in-code model/config dictionaries:
  - `boot_logo.py:SERIAL_FLASH_CONFIGS`
  - `models/registry.py:_MODEL_REGISTRY`
- safety token constant: `core/safety.py:CONFIRMATION_TOKEN` (`WRITE`)
- Streamlit session state keys initialized in `streamlit_ui.py:_init_session_state`

See `repodocs/CONFIGURATION.md` for a full matrix.

## Typical Workflows

- First-run connection validation:
  - `baofeng-logo-flasher ports`
  - `baofeng-logo-flasher detect --port ...`
- Safe trial:
  - `upload-logo-serial --dry-run`
- Production flash:
  - `upload-logo-serial --write --confirm WRITE`
- Optional protocol diagnostics:
  - `--debug-bytes --debug-dir out/logo_debug`

## Troubleshooting

See `repodocs/TROUBLESHOOTING.md`.

High-frequency failure classes in code paths:
- serial open/permission failures (`protocol/uv5rm_transport.py:open`)
- handshake ACK mismatch (`protocol/logo_protocol.py:LogoUploader.handshake`)
- write-denied safety gate (`core/safety.py:require_write_permission`)
- frame/data ACK mismatch during image transfer (`protocol/logo_protocol.py:LogoUploader.send_image_data`)

## Safety Notes

Potentially destructive operations:
- Any path that writes to radio memory/protocol (`upload-logo-serial`, UI write mode)

Guardrails in code:
- explicit `--write` + confirmation token (`WRITE`) for CLI write paths
- simulation mode available in both CLI/UI

References:
- `cli.py:confirm_write_with_details`
- `core/safety.py:require_write_permission`
- `streamlit_ui.py:_do_flash`

## Contributing (Light)

For contributors:
- Start with `repodocs/ARCHITECTURE.md`, `repodocs/RUNTIME_FLOW.md`, and `repodocs/FILE_MAP.md`.
- Keep safety checks centralized in `core/safety.py`.
- Prefer shared core actions (`core/actions.py`) over duplicating write logic in CLI/UI.

## License

Project metadata declares `MIT` in `pyproject.toml`.

## Project Structure

Top-level runtime-relevant layout:

- `src/baofeng_logo_flasher/cli.py` – CLI entrypoint and commands
- `src/baofeng_logo_flasher/streamlit_ui.py` – Streamlit UI entrypoint and pages
- `src/baofeng_logo_flasher/core/` – shared safety/parsing/results/action/message logic
- `src/baofeng_logo_flasher/protocol/` – serial transport + UV5R/A5 protocols
- `src/baofeng_logo_flasher/boot_logo.py` – A5 flash helpers and model configs
- `src/baofeng_logo_flasher/models/` – model registry and capability reporting
- `src/baofeng_logo_flasher/ui/` – reusable Streamlit components
