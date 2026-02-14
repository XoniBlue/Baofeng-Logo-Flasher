# User Guide

This guide is the detailed end-user reference. `README.md` remains a Quick Start.

## Install

### Requirements

- Python 3.9+
- Serial access to the radio (USB cable + OS drivers/permissions)

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[ui]"
```

### Windows (PowerShell)

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[ui]"
```

### CLI-only Install

```bash
pip install -e .
```

### Verify Install

```bash
baofeng-logo-flasher --help
baofeng-logo-flasher ports
```

Optional UI check:

```bash
baofeng-logo-flasher-ui
```

## Common Tasks (CLI)

### 1) List Ports

```bash
baofeng-logo-flasher ports
```

### 2) List Supported Models

```bash
baofeng-logo-flasher list-models
```

### 3) Detect Connected Radio

```bash
baofeng-logo-flasher detect --port /dev/ttyUSB0
```

### 4) Simulate A5 Serial Logo Upload (Safe Dry Run)

```bash
baofeng-logo-flasher upload-logo-serial \
  --port /dev/ttyUSB0 \
  --in my_logo.png \
  --model UV-5RM \
  --dry-run
```

### 5) Real A5 Serial Logo Upload

```bash
baofeng-logo-flasher upload-logo-serial \
  --port /dev/ttyUSB0 \
  --in my_logo.png \
  --model UV-5RM \
  --write --confirm WRITE
```

## UI Workflow

```bash
baofeng-logo-flasher-ui
```

In the browser:
1. Select model + port
2. Upload/select image (auto converted to model size where applicable)
3. Run in simulate mode first, then enable write mode only when ready

## Debugging Protocol Bytes

CLI:

```bash
baofeng-logo-flasher upload-logo-serial \
  --port /dev/ttyUSB0 --in logo.bmp --model UV-5RM \
  --write --confirm WRITE \
  --debug-bytes --debug-dir out/logo_debug
```

UI:
- enable the debug-bytes toggle (writes to `out/streamlit_logo_debug`)

## Safety Expectations

- Any non-simulated write requires explicit confirmation gates.
- Prefer a dry-run/simulation before a live write.
- Use stable power and a known-good cable during writes.

For protocol and image format details, see `docs/protocol-spec.md`.

