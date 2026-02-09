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

### B) Legacy logo upload path (`upload-logo`)

1. `cli.py:upload_logo` opens `UV5RMTransport`, then `UV5RMProtocol`.
2. Detects model with `UV5RMProtocol.identify_radio`.
3. Resolves target region via `BootLogoService.resolve_logo_region` or discovery (`discover_logo_region`).
4. Prepares bytes via `BootLogoService.prepare_logo_bytes` + `bmp_utils.validate_bmp_bytes`.
5. If not dry-run, performs explicit CLI confirmation (`confirm_write_with_details`).
6. Writes blocks with `UV5RMProtocol.write_block` loop.
7. Reads back with `UV5RMProtocol.read_block` loop and compares.

### C) Clone download path (`read_clone`)

1. `cli.py:read_clone` constructs transport/protocol.
2. `UV5RMProtocol.identify_radio`.
3. `UV5RMProtocol.download_clone` reads address ranges.
4. Optional output file write by CLI command.

### D) Logo backup/download path (`download-logo` and UI backup mode)

1. `cli.py:download_logo` or `streamlit_ui.py:_do_download_logo`.
2. Calls `boot_logo.py:read_logo` for non-A5 models.
3. Converts raw bytes to BMP with `boot_logo.py:convert_raw_to_bmp`.
4. Writes/sends BMP output.

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
