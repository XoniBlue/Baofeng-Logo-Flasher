# Baofeng Logo Flasher

[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](pyproject.toml)
[![CLI + Streamlit](https://img.shields.io/badge/interface-CLI%20%2B%20Streamlit-0A7EA4.svg)](src/baofeng_logo_flasher)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](pyproject.toml)

Reliable boot-logo flashing for Baofeng UV-5RM and UV-17-family radios.

## Overview

This repository provides a practical, working path for boot-logo flashing with:
- direct serial A5 flashing (`upload-logo-serial`)
- Streamlit UI backed by the same core logic

Protocol-critical behavior implemented here:
- UV-5RM/UV-17 A5 `CMD_WRITE` uses **chunk-index addressing** (`0,1,2,...`), not byte offsets.

## Support Matrix

| Model | Direct A5 Flash | Address Mode | Status |
|---|---|---|---|
| `UV-5RM` | Yes (`upload-logo-serial`) | `chunk` | Working |
| `UV-17Pro` | Yes (`upload-logo-serial`) | `chunk` | Configured |
| `UV-17R` | Yes (`upload-logo-serial`) | `chunk` | Configured |

## Prerequisites

- Python `3.9+`
- USB serial cable connected to radio
- macOS/Linux shell examples below (Windows users can adapt paths/activation)

## Install (From Scratch)

Clone and enter the repo:

```bash
git clone https://github.com/XoniBlue/Baofeng-Logo-Flasher.git
cd Baofeng-Logo-Flasher
```

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install CLI + Streamlit UI:

```bash
pip install -e ".[ui]"
```

Verify install:

```bash
baofeng-logo-flasher --help
baofeng-logo-flasher-ui --help
```

Optional: use Make targets:

```bash
make install
```

## Use (CLI)

1. Find your serial port:

```bash
baofeng-logo-flasher ports
```

2. Check supported model names:

```bash
baofeng-logo-flasher list-models
```

3. Run a dry operation first (no write to radio):

```bash
baofeng-logo-flasher upload-logo-serial \
  --port /dev/cu.Plser \
  --in my_logo.png \
  --model UV-5RM
```

4. Run a real write:

```bash
baofeng-logo-flasher upload-logo-serial \
  --port /dev/cu.Plser \
  --in my_logo.png \
  --model UV-5RM \
  --write --confirm WRITE
```

## Use (Web UI)

Start Streamlit:

```bash
baofeng-logo-flasher-ui
```

Or:

```bash
make serve
```

In the app:
1. `Step 1 · Connection`: select model/port (or let auto-detect settle).
2. `Step 2 · Logo`: upload image (auto-converted to radio format).
3. `Step 3 · Flash`: keep `Write mode` off for simulation; enable it only when ready.

## Notes

- For UV-5RM/UV-17 family, A5 writes use chunk-index addressing internally.
- Direct A5 logo read-back is not implemented in this repo.

## Useful Commands

| Command | Purpose |
|---|---|
| `baofeng-logo-flasher --help` | Full CLI help |
| `baofeng-logo-flasher list-models` | Supported model configs |
| `baofeng-logo-flasher show-model-config UV-5RM` | Effective model/protocol settings |
| `baofeng-logo-flasher upload-logo-serial ...` | Direct serial logo upload |

## Byte Debug Mode

```bash
baofeng-logo-flasher upload-logo-serial \
  --port /dev/cu.Plser \
  --in my_logo.png \
  --model UV-5RM \
  --write --confirm WRITE \
  --debug-bytes --debug-dir out/logo_debug
```

Artifacts:
- `image_payload.bin`
- `write_payload_stream.bin`
- `write_frames.bin`
- `preview_row_major.png`
- `manifest.json`

## Repository Layout

| Path | Role |
|---|---|
| `src/baofeng_logo_flasher/cli.py` | CLI entrypoint |
| `src/baofeng_logo_flasher/streamlit_ui.py` | Streamlit UI entrypoint |
| `src/baofeng_logo_flasher/protocol/logo_protocol.py` | A5 framing/chunking/CRC/image payload |
| `src/baofeng_logo_flasher/boot_logo.py` | Model serial-flash config/address mode |
| `src/baofeng_logo_flasher/core/actions.py` | Shared CLI/UI workflow logic |
| `tests/` | Regression tests |
| `tools/` | Optional developer diagnostics |

## Documentation

Top-level docs:
- `TROUBLESHOOTING.md`
- `LOGO_PROTOCOL.md`
- `DEVELOPMENT.md`
- `CHANGELOG.md`

Supplemental docs:
- `docs/UI_BEHAVIOR.md`
- `docs/IMAGE_LAYOUT.md`

## Contributing Notes

Tests and tools remain in-repo for reliability and long-term maintenance.
End users only need install + flash commands from this README.

## License

MIT
