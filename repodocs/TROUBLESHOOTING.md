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
- reconnect cable and confirm the selected A5 model profile, then retry.

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
- `core/actions.py:flash_logo_serial` error handling
- `protocol/logo_protocol.py:LogoUploader.send_image_data`

## 5) Symptom: UI fails to launch with missing package error

Likely cause:
- optional UI dependency not installed.

Verify/Fix:
- run `pip install -e ".[ui]"`

Code reference:
- `streamlit_ui.py` top-level `try/except ImportError`

## 6) Symptom: image rejected (size/format)

Likely cause:
- wrong dimensions/BMP constraints for specific path.

Verify:
- ensure conversion to target size (typically 160x128 for A5 configs).

Fix:
- use UI conversion or validate via CLI before write.

Code references:
- `bmp_utils.py:validate_bmp_bytes`
- `streamlit_ui.py:_process_image_for_radio`

## 7) Symptom: manual/advanced API mismatch

Likely cause:
- calling internal helper APIs that are not part of the A5 upload flow contract.

Verify:
- inspect current public flow in `core/actions.py:flash_logo_serial`.

Fix:
- route custom integrations through `flash_logo_serial` and `boot_logo.flash_logo`.
