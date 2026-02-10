# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

### Changed
- Streamlit app simplified to two tabs:
  - `Boot Logo Flasher`
  - `Capabilities`
- Removed Streamlit `Tools & Inspect` and `Verify/Patch` pages.
- Removed CLI clone/patch inspection commands:
  - `scan-logo`, `scan-bitmaps`, `inspect-img`, `verify-image`, `patch-logo`, `flash-logo` (clone patch flow)

### Removed
- Deprecated clone patch/verification code paths and modules no longer used by active workflow:
  - `logo_patcher.py`
  - `protocol_verifier.py`
  - `bitmap_scanner.py`

## [0.2.0] - 2026-02-08

### Added
- Direct A5 serial flashing command: `upload-logo-serial`.
- Byte-debug artifact export for serial flashing (`--debug-bytes`, `--debug-dir`).
- Protocol tests for frame construction and payload behavior.
- Developer tooling:
  - `tools/logo_payload_tools.py`
  - `tools/generate_logo_probes.py`

### Changed
Fixed (in this release) UV-5RM/UV-17-family write addressing for A5 `CMD_WRITE`:
  - switched to chunk-index addressing (`0,1,2,...`) for configured models.
Streamlit and CLI now use aligned serial flashing behavior through shared core actions.
Documentation overhaul for root-level discoverability and user-first workflows.

### Removed
Redundant legacy helper scripts replaced by CLI commands:
  - `tools/inspect_img.py`
  - `tools/scan_bitmap_candidates.py`
Historical/local artifacts from tracked repository content.

### Notes
- In previous versions, flash could appear successful but display would show a top-line fragment with gray/garbled remainder. This issue is now resolved in current releases.
