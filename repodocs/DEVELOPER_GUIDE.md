# Developer Guide

## Local Run

### CLI

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[ui]"
baofeng-logo-flasher --help
```

### UI

```bash
baofeng-logo-flasher-ui
```

## Debugging

- Enable operation-level byte dumps with `--debug-bytes` on serial upload command.
- Inspect generated files under `out/logo_debug` or `out/streamlit_logo_debug`.
- Use captured logs embedded in `OperationResult.logs` (`core/actions.py:_capture_logs`).

## Logging Strategy

- CLI configures Rich logging in `cli.py` (global `logging.basicConfig`).
- Core actions capture logs with `_capture_logs` and return them as result metadata/log lines.

## Extending Features Safely

1. Keep write gating centralized:
- Always call `core/safety.py:require_write_permission` before write operations.

2. Reuse `OperationResult`:
- Return structured success/failure via `core/results.py:OperationResult`.

3. Keep protocol-specific details in `protocol/`:
- Avoid embedding frame-level logic in CLI/UI files.

4. Keep model metadata synchronized:
- Update both registry and serial flash config sources if needed.
- Current split sources (`models/registry.py` vs `boot_logo.py:SERIAL_FLASH_CONFIGS`) require careful consistency checks.

## Repository Conventions (observed)

- Shared safety and parsing in `core/`.
- CLI and UI delegate heavy operations to core/domain modules.
- `models/registry.py` used for capabilities and model lookup.

## Testing Strategy (recommended)

Even without relying on existing tests here, add/maintain tests around:
- `core/safety.py` write gating matrix (simulate/write/token/interactive)
- `protocol/logo_protocol.py` frame construction and CRC (`build_frame`, `crc16_xmodem`)
- `boot_logo.py` conversion/dispatch logic
- model-registry consistency checks between `models/registry.py` and `boot_logo.py:SERIAL_FLASH_CONFIGS`

## Current Brittle Areas

- Duplicate `UV-17R` registration in `models/registry.py:_init_registry` (last write wins).
- `core/actions.py:read_clone` interface mismatch to `UV5RMProtocol.download_clone` signature.
- Multiple model truth sources can drift.
