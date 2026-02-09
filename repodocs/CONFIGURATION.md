# Configuration

## Configuration Sources

1. CLI flags and options in `src/baofeng_logo_flasher/cli.py`
2. Static model config dictionaries:
- `src/baofeng_logo_flasher/boot_logo.py:SERIAL_FLASH_CONFIGS`
- `src/baofeng_logo_flasher/boot_logo.py:MODEL_CONFIGS`
- `src/baofeng_logo_flasher/models/registry.py:_MODEL_REGISTRY`
3. Safety constants:
- `src/baofeng_logo_flasher/core/safety.py:CONFIRMATION_TOKEN`
4. UI session state defaults:
- `src/baofeng_logo_flasher/streamlit_ui.py:_init_session_state`

No environment variables are consumed by runtime code.

## Global Defaults

- Python: `>=3.9` (`pyproject.toml`)
- Core deps: `pyserial`, `pillow`, `rich`, `typer` (`pyproject.toml`)
- Optional UI dep: `streamlit` (`pyproject.toml` optional extra `ui`)
- Safety confirmation token: `WRITE` (`core/safety.py`)

## Key CLI Knobs

### `upload-logo-serial` (`cli.py:upload_logo_serial`)

- `--port` required
- `--in` required input image path
- `--model` default `UV-5RM`
- `--dry-run` default `False`
- `--write` default `False` (must be set for real writes)
- `--confirm` token for non-interactive confirmation (`WRITE`)
- `--debug-bytes` default `False`
- `--debug-dir` default `out/logo_debug`
- `--write-addr-mode` default `auto` (`auto|byte|chunk`)

Precedence:
- `--write-addr-mode auto` -> use model config `write_addr_mode`
- explicit `byte`/`chunk` -> overrides config

### `upload-logo` (`cli.py:upload_logo`)

- Region selection precedence:
1. `--logo-start` + `--logo-length`
2. `--discover` + scan range args
3. model default region via `MODEL_CONFIGS`

- Safety controls:
- `--dry-run` bypasses actual write
- non-dry writes require `--write` and confirmation workflow
- `--confirm` supports non-interactive runs

### `download-logo` (`cli.py:download_logo`)

- `--raw` toggles BMP validation
- explicit region args or discovery args mirror upload precedence

## UI Runtime State Knobs

Initialized in `streamlit_ui.py:_init_session_state`:
- `selected_model`
- `selected_port`
- `simulate_mode`
- connection probe/polling keys (`connection_probe`, `connection_poll_meta`, etc.)
- write mode keys from `ui/components.py:init_write_mode_state`

Operational toggles in UI:
- backup mode (`logo_action_backup_mode`)
- write mode (`step3_write_mode`)
- debug bytes (`step3_debug_bytes`)

## Data/Artifact Paths

- Streamlit temp BMP during flash: OS temp via `tempfile.NamedTemporaryFile` (`streamlit_ui.py:_do_flash`)
- Streamlit backup of last flashed image:
  - `backups/last_flash/<model>.bmp`
  - `backups/last_flash/<model>.json`
  (`streamlit_ui.py:_save_last_flash_backup`)
- A5 debug artifacts default:
  - CLI: `out/logo_debug`
  - UI: `out/streamlit_logo_debug`
  (`logo_protocol.py:dump_logo_debug_artifacts`)
