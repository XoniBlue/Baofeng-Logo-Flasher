# Safety

## High-Risk Operations

These operations can write to device memory/protocol state:
- CLI `upload-logo-serial`
- UI Step 3 flash when write mode is enabled

Relevant code:
- `cli.py:upload_logo_serial`
- `streamlit_ui.py:_do_flash`

## Built-In Guardrails

- Central write gate: `core/safety.py:require_write_permission`
- Confirmation token requirement (`WRITE`) for non-interactive workflows: `core/safety.py:CONFIRMATION_TOKEN`
- Simulate/dry-run modes to avoid writing:
  - CLI: `--dry-run`
  - UI: write mode toggle off (simulation)

## Irreversible/Uncertain Areas

- A5 logo write is a direct serial protocol path (`protocol/logo_protocol.py`) and can fail mid-transfer if cable/power is unstable.
- A5 logo write is one-way in this app; direct radio read-back is not implemented.

## Recommended Operator Workflow

1. Confirm correct serial port and radio detection first (`ports`, `detect`).
2. Run simulation before any write.
3. Use stable power and a known-good data cable.
4. Keep debug artifacts for post-failure analysis when needed (`--debug-bytes`).
5. Preserve local backup artifacts (`backups/last_flash/*`) produced by UI after successful writes.

## Safety-Related Failure Signals

- `WritePermissionError`: write explicitly blocked by policy.
- ACK mismatch/timeouts during handshake/write: likely transport or mode issue.
- Readback verification mismatch: data integrity issue; do not assume successful flash.
