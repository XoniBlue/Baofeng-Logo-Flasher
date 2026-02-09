# Baofeng Logo Flasher

<p align="left">
  <a href="https://www.python.org/"><img alt="Python" src="https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white"></a>
  <a href="https://github.com/XoniBlue/Baofeng-Logo-Flasher/blob/main/pyproject.toml"><img alt="CLI" src="https://img.shields.io/badge/Interface-CLI-222222?logo=gnubash&logoColor=white"></a>
  <a href="https://github.com/XoniBlue/Baofeng-Logo-Flasher/blob/main/src/baofeng_logo_flasher/streamlit_ui.py"><img alt="Streamlit UI" src="https://img.shields.io/badge/Interface-Streamlit_UI-FF4B4B?logo=streamlit&logoColor=white"></a>
  <a href="https://github.com/XoniBlue/Baofeng-Logo-Flasher/blob/main/pyproject.toml"><img alt="License" src="https://img.shields.io/badge/License-MIT-22AA66?logo=open-source-initiative&logoColor=white"></a>
  <a href="https://github.com/XoniBlue/Baofeng-Logo-Flasher/blob/main/src/baofeng_logo_flasher/cli.py"><img alt="Typer" src="https://img.shields.io/badge/CLI-Typer-0F766E"></a>
</p>

Local, safety-gated boot logo flashing for supported Baofeng radios using serial USB.

---

## Quick Navigation

- [1) Project overview](#1-project-overview)
- [2) What this tool does / does not do](#2-what-this-tool-does--does-not-do)
- [3) Requirements](#3-requirements)
- [4) Installation](#4-installation)
- [5) CLI usage](#5-cli-usage)
- [6) Local UI usage (Streamlit)](#6-local-ui-usage-streamlit)
- [7) Step-by-step flashing walkthrough](#7-step-by-step-flashing-walkthrough)
- [8) Safety notes](#8-safety-notes)
- [9) Troubleshooting](#9-troubleshooting)
- [10) Where to get help / report issues](#10-where-to-get-help--report-issues)

---

## 1) Project overview

Baofeng Logo Flasher prepares and flashes a boot logo to compatible radios over a local serial connection.

### Direct serial flashing path (recommended)

| Model | Command path | Status |
|---|---|---|
| `UV-5RM` | `upload-logo-serial` / Streamlit Step 3 | Supported |
| `UV-17Pro` | `upload-logo-serial` / Streamlit Step 3 | Supported |
| `UV-17R` | `upload-logo-serial` / Streamlit Step 3 | Supported |

### Other models present in registry/capabilities

`DM-32UV`, `UV-5RH Pro`, `UV-17R Pro`, `UV-5R`, `UV-5R-ORIG`, `UV-82`, `UV-6`, `F-11`, `A-58`, `UV-5G`, `F-8HP`, `UV-82HP`, `82X3`

---

## 2) What this tool does / does not do

### What it does

- Flashes boot logos locally over serial USB.
- Accepts image input and converts it to radio-compatible format.
- Enforces explicit write safety gates (`--write` + confirmation token).
- Offers both CLI and local Streamlit UI.

### What it does not do

- Does not provide hosted/cloud/browser-based flashing.
- Does not implement direct A5 logo read-back for `UV-5RM` / `UV-17` A5 models.
- Does not guarantee universal support across all Baofeng firmware variants.

---

## 3) Requirements

| Requirement | Details |
|---|---|
| OS | macOS, Linux, or Windows |
| Python | `3.9+` |
| Hardware | Compatible radio + data-capable USB cable |
| Access | Serial/COM port permissions |

---

## 4) Installation

### Option A: Makefile setup (recommended)

```bash
git clone https://github.com/XoniBlue/Baofeng-Logo-Flasher.git
cd Baofeng-Logo-Flasher
make install
```

`make install` will:
- create `.venv` if missing
- install project dependencies including UI and dev extras (`.[ui,dev]`)

### Option B: Manual virtual environment

```bash
git clone https://github.com/XoniBlue/Baofeng-Logo-Flasher.git
cd Baofeng-Logo-Flasher
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[ui]"
```

Windows PowerShell activation:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -e ".[ui]"
```

Verify CLI install:

```bash
baofeng-logo-flasher --help
```

---

## 5) CLI usage

### Discover ports and models

```bash
baofeng-logo-flasher ports
baofeng-logo-flasher list-models
```

### Flash logo with serial A5 path

Dry run first (no write):

```bash
baofeng-logo-flasher upload-logo-serial \
  --port /dev/cu.usbserial-XXXX \
  --in my_logo.png \
  --model UV-5RM
```

Real write:

```bash
baofeng-logo-flasher upload-logo-serial \
  --port /dev/cu.usbserial-XXXX \
  --in my_logo.png \
  --model UV-5RM \
  --write --confirm WRITE
```

Debug bytes (optional):

```bash
baofeng-logo-flasher upload-logo-serial \
  --port /dev/cu.usbserial-XXXX \
  --in my_logo.png \
  --model UV-5RM \
  --write --confirm WRITE \
  --debug-bytes --debug-dir out/logo_debug
```

---

## 6) Local UI usage (Streamlit)

### Launch methods

Background mode:

```bash
make start
```

Foreground mode:

```bash
make serve
```

Console script:

```bash
baofeng-logo-flasher-ui
```

Direct Streamlit command:

```bash
PYTHONPATH=src streamlit run src/baofeng_logo_flasher/streamlit_ui.py
```

Open locally:
- `http://localhost:8501`

Stop background server:

```bash
make stop
```

---

## 7) Step-by-step flashing walkthrough

1. Connect the radio with a data-capable USB cable and power it on.
2. Start the UI (`make start`) and open `http://localhost:8501`.
3. In `Step 1 · Connection`, choose the model and serial port.
4. In `Step 2 · Logo`, upload your source image.
5. Confirm conversion is shown as ready.
6. In `Step 3 · Flash`, keep **Write mode** off and run simulation first.
7. If simulation results look correct, enable **Write mode**.
8. Execute the flash and wait for completion.
9. Power-cycle the radio if needed to display the new logo.

CLI equivalent:

1. `baofeng-logo-flasher ports`
2. Dry run with `upload-logo-serial`
3. Real write with `--write --confirm WRITE`

---

## 8) Safety notes

> Write carefully. Serial flashing is low-level I/O and should be treated as a deliberate operation.

- Run simulation/dry run before real write.
- CLI writes require both `--write` and `--confirm WRITE`.
- Keep cable and power stable during write.
- Verify model and port before flashing.
- A5 model direct read-back is not implemented in this repo.

---

## 9) Troubleshooting

### Common fixes

- `command not found`
  - Reinstall in your active environment: `pip install -e .` or `pip install -e ".[ui]"`
- Missing dependency/import errors
  - Activate the right venv and reinstall dependencies.
- Serial port not working
  - Run `baofeng-logo-flasher ports` and use the full device path.
- Write is blocked
  - Include both `--write` and `--confirm WRITE`.
- UI appears stale
  - Restart UI: `make stop` then `make start`.
- Need deeper inspection
  - Use `--debug-bytes` and inspect `out/logo_debug/manifest.json`.

---

## 10) Where to get help / report issues

### Local docs

- `TROUBLESHOOTING.md`
- `LOGO_PROTOCOL.md`
- `docs/UI_BEHAVIOR.md`
- `docs/IMAGE_LAYOUT.md`

### Issues / feature requests

- https://github.com/XoniBlue/Baofeng-Logo-Flasher/issues

---

## License

MIT
