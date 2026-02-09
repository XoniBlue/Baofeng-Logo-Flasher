# Troubleshooting

## 1) Symptom: "Cannot open port ..."

Likely cause:
- port path invalid, already in use, permission denied.

Verify:
- run `baofeng-logo-flasher ports`
- ensure no other app owns the serial port.

Fix:
- use the exact listed device path / COM port
- close other serial tools
- fix OS serial permissions/drivers

Code references:
- `protocol/uv5rm_transport.py:UV5RMTransport.open`

## 2) Symptom: handshake failed or no ACK (0x06)

Likely cause:
- radio not powered/connected, wrong mode/profile, unstable cable.

Verify:
- `baofeng-logo-flasher detect --port ...`
- try again after power cycle.

Fix:
- reconnect cable, confirm model path (A5 vs legacy), retry.

Code references:
- `protocol/logo_protocol.py:LogoUploader.handshake`
- `protocol/uv5rm_transport.py:handshake`

## 3) Symptom: write denied before any serial write

Likely cause:
- `--write` missing, bad `--confirm`, unknown model/region in safety context.

Verify:
- check command includes `--write --confirm WRITE`.

Fix:
- provide explicit write/confirm flags, or run dry-run intentionally.

Code references:
- `core/safety.py:require_write_permission`
- `cli.py:confirm_write_with_details`

## 4) Symptom: read-back verification failed

Likely cause:
- serial instability, incorrect target region/path.

Verify:
- rerun with stable connection, compare logs.

Fix:
- retry with known-good cable/port and correct model profile.

Code references:
- `cli.py:upload_logo` readback compare
- `core/actions.py:write_logo` verification compare

## 5) Symptom: UI fails to launch with missing package error

Likely cause:
- optional UI dependency not installed.

Verify/Fix:
- run `pip install -e ".[ui]"`

Code reference:
- `streamlit_ui.py` top-level `try/except ImportError`

## 6) Symptom: backup/download unavailable for UV-5RM/UV-17 A5 models

Likely cause:
- A5 read-back not implemented in app.

Verify:
- UI backup mode info message or thrown error path.

Fix:
- use last-flash local backup if available; direct A5 read-back is not implemented.

Code references:
- `streamlit_ui.py:tab_boot_logo_flasher` (backup mode branch)
- `boot_logo.py:read_logo` (raises for `protocol == "a5_logo"`)

## 7) Symptom: image rejected (size/format)

Likely cause:
- wrong dimensions/BMP constraints for specific path.

Verify:
- ensure conversion to target size (typically 160x128 for A5 configs).

Fix:
- use UI conversion or validate via CLI before write.

Code references:
- `bmp_utils.py:validate_bmp_bytes`
- `boot_logo.py:convert_bmp_to_raw`
- `streamlit_ui.py:_process_image_for_radio`

## 8) Symptom: manual/advanced API mismatch

Likely cause:
- `core/actions.py:read_clone` passes `progress_cb` into `UV5RMProtocol.download_clone`, but protocol method currently does not accept that parameter.

Verify:
- inspect signatures in both files.

Fix:
- update one side of the interface before using that core function path directly.
