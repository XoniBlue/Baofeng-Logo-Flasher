# Architecture

## Overview

The codebase is split into five runtime layers:

1. Entrypoints:
- `src/baofeng_logo_flasher/cli.py`
- `src/baofeng_logo_flasher/streamlit_ui.py`

2. Shared core logic:
- `src/baofeng_logo_flasher/core/safety.py`
- `src/baofeng_logo_flasher/core/actions.py`
- `src/baofeng_logo_flasher/core/parsing.py`
- `src/baofeng_logo_flasher/core/results.py`
- `src/baofeng_logo_flasher/core/messages.py`

3. Protocol/IO layer:
- `src/baofeng_logo_flasher/protocol/uv5rm_transport.py` (serial primitives)
- `src/baofeng_logo_flasher/protocol/logo_protocol.py` (A5 logo protocol)

4. Domain services:
- `src/baofeng_logo_flasher/boot_logo.py` (A5 flash orchestration + model config bridge)
- `src/baofeng_logo_flasher/logo_codec.py` (bitmap packing)
- `src/baofeng_logo_flasher/bmp_utils.py` (BMP validation)

5. Model/capability registry:
- `src/baofeng_logo_flasher/models/registry.py`

## Text Dependency Diagram

`CLI/UI` -> `core/actions + core/safety + models/registry` -> `boot_logo` -> `protocol/*` -> `pyserial`

Additional path:
- `CLI/UI` -> `bmp_utils` / `logo_codec` / `Pillow` for image preprocessing.

## Module Boundaries

- `core/safety.py`
  - Single write-permission gate (`require_write_permission`), shared by CLI/UI and core actions.
- `core/actions.py`
  - Operation-level wrappers returning `OperationResult`.
  - Bridges UI/CLI with protocol functions.
- `protocol/uv5rm_transport.py`
  - Raw serial reads/writes, ACK handling, block-level read/write.
- `protocol/uv5rm_protocol.py`
  - Radio identification helpers used by CLI `detect`.
- `protocol/logo_protocol.py`
  - A5 frame protocol: CRC16, command sequence, chunked image write.
- `boot_logo.py`
  - Model-specific A5 configs (`SERIAL_FLASH_CONFIGS`) and protocol dispatch.
- `models/registry.py`
  - Central model metadata/capabilities for reporting and config lookups.

## Key Abstractions

- `SafetyContext` (`core/safety.py`)
- `OperationResult` (`core/results.py`)
- `UV5RMTransport` (`protocol/uv5rm_transport.py`)
- `UV5RMProtocol` (`protocol/uv5rm_protocol.py`)
- `LogoUploader` (`protocol/logo_protocol.py`)
- `ModelConfig`, `ModelCapabilities` (`models/registry.py`)

## Extension Points

- Add models and capability metadata via `models/registry.py:_init_registry`.
- Add new A5-capable model metadata in `models/registry.py` and consume via `boot_logo`.
- Extend CLI by adding Typer commands in `cli.py` that call `core/actions.py`.
- Extend UI by adding tabs/components in `streamlit_ui.py` and `ui/components.py`.

## Known Architecture Tensions

- `protocol/uv5rm_protocol.py` still exists for detection/protocol compatibility, while the active product path is exclusively A5 logo upload.
