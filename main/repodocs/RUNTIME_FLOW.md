# Runtime Flow

## Startup Sequence

### CLI path

1. Console script resolves to `baofeng_logo_flasher.cli:main` (`pyproject.toml`).
2. `cli.py:main` invokes Typer app (`app()`).
3. Requested command executes command function.

### UI path

1. Console script resolves to `baofeng_logo_flasher.streamlit_ui:launch`.
2. `streamlit_ui.py:launch` calls `streamlit.web.bootstrap.run()` with module path.
3. `streamlit_ui.py:main` configures page, initializes session state (`_init_session_state`), renders tabs.

## Main Operations

### A) Direct serial logo flash (A5)

CLI (`upload-logo-serial`) and UI (`_do_flash`) converge on shared core action:

1. Build safety context:
- CLI: `core/safety.py:create_cli_safety_context`
- UI: `core/safety.py:create_streamlit_safety_context`

2. Enforce write gate:
- `core/safety.py:require_write_permission`

3. Execute action:
- `core/actions.py:flash_logo_serial`
- delegates to `boot_logo.py:flash_logo`
- dispatches to `boot_logo.py:_flash_logo_a5_protocol` when `config["protocol"] == "a5_logo"`
- calls `protocol/logo_protocol.py:upload_logo`

4. A5 protocol call chain:
- `LogoUploader.open`
- `LogoUploader.handshake`
- `LogoUploader.enter_logo_mode`
- `LogoUploader.send_init_frame`
- `LogoUploader.send_config_frame`
- `LogoUploader.send_setup_frame`
- `LogoUploader.send_image_data`
- `LogoUploader.send_completion_frame`
- `LogoUploader.close` (finally)

### B) Removed Legacy Paths

Legacy clone/block logo flows (`upload-logo`, `download-logo`, UI backup/download branch)
have been removed. Runtime supports A5 serial logo upload only.

## Shutdown / Cleanup

- CLI command handlers close transport in `finally` blocks where used.
- A5 uploader always closes serial in `LogoUploader.upload_logo` `finally`.
- UI `_do_flash` deletes temp BMP file in `finally` and resets polling state.

## Error Handling Path

- Serial/protocol exceptions bubble as:
  - `RadioTransportError`, `RadioBlockError`, `RadioNoContact` (`uv5rm_transport.py`)
  - `LogoProtocolError` (`logo_protocol.py`)
  - `BootLogoError` (`boot_logo.py`)
  - `WritePermissionError` (`core/safety.py`)
- CLI generally prints friendly message + exits with non-zero status.
- UI displays `st.error/st.warning` and contextual hints.
