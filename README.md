# Baofeng Logo Flasher

Reliable local boot-logo flashing for supported Baofeng radios, with both CLI and Streamlit UI.

## 1) Project overview

Baofeng Logo Flasher lets you prepare and flash a boot logo to compatible radios over a USB serial cable.

Supported in the direct serial flashing path (`upload-logo-serial` / Streamlit Step 3):
- `UV-5RM`
- `UV-17Pro`
- `UV-17R`

Also present in project model/config registries (capabilities, legacy/experimental flows):
- `DM-32UV`
- `UV-5RH Pro`
- `UV-17R Pro`
- `UV-5R`
- `UV-5R-ORIG`
- `UV-82`
- `UV-6`
- `F-11`
- `A-58`
- `UV-5G`
- `F-8HP`
- `UV-82HP`
- `82X3`

## 2) What this tool does / does not do

What it does:
- Flashes boot logos locally over serial.
- Accepts image input and converts it for target radio requirements.
- Provides safety gating for writes (`--write` and confirmation token).
- Supports both command line and local Streamlit UI.

What it does not do:
- No hosted/cloud/browser flashing service.
- No direct A5 logo read-back for `UV-5RM` / `UV-17` A5 models.
- No guarantee for every Baofeng variant/firmware outside listed supported flash path.

## 3) Requirements

- OS: macOS, Linux, or Windows (with Python and serial access).
- Python: `3.9+`.
- Hardware: compatible radio + data-capable USB cable.
- Access to serial/COM port permissions on your OS.

## 4) Installation

### Option A (recommended): Makefile setup

```bash
git clone https://github.com/XoniBlue/Baofeng-Logo-Flasher.git
cd Baofeng-Logo-Flasher
make install
```

What `make install` does:
- creates `.venv` if needed
- installs package with `.[ui,dev]`

### Option B: manual venv setup

```bash
git clone https://github.com/XoniBlue/Baofeng-Logo-Flasher.git
cd Baofeng-Logo-Flasher
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[ui]"
```

On Windows PowerShell, activate with:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -e ".[ui]"
```

Verify CLI command is available:

```bash
baofeng-logo-flasher --help
```

## 5) CLI usage

### Useful discovery commands

```bash
baofeng-logo-flasher ports
baofeng-logo-flasher list-models
```

### Recommended flashing flow (A5 serial path)

1. Dry run first (no write):

```bash
baofeng-logo-flasher upload-logo-serial \
  --port /dev/cu.usbserial-XXXX \
  --in my_logo.png \
  --model UV-5RM
```

2. Real write:

```bash
baofeng-logo-flasher upload-logo-serial \
  --port /dev/cu.usbserial-XXXX \
  --in my_logo.png \
  --model UV-5RM \
  --write --confirm WRITE
```

Optional byte/frame diagnostics:

```bash
baofeng-logo-flasher upload-logo-serial \
  --port /dev/cu.usbserial-XXXX \
  --in my_logo.png \
  --model UV-5RM \
  --write --confirm WRITE \
  --debug-bytes --debug-dir out/logo_debug
```

## 6) Local UI usage (Streamlit)

Start locally with Makefile:

```bash
make start
```

Or run in foreground:

```bash
make serve
```

Or launch via console script:

```bash
baofeng-logo-flasher-ui
```

Or run Streamlit directly:

```bash
PYTHONPATH=src streamlit run src/baofeng_logo_flasher/streamlit_ui.py
```

Open:
- `http://localhost:8501`

Stop background UI:

```bash
make stop
```

## 7) Step-by-step flashing walkthrough

1. Connect radio via USB and power it on.
2. Start UI (`make start`) and open `http://localhost:8501`.
3. In **Step 1 · Connection**, select model and serial port.
4. In **Step 2 · Logo**, upload your image.
5. Confirm the app reports conversion to target size and readiness.
6. In **Step 3 · Flash**, leave **Write mode** off and run simulation first.
7. If simulation looks good, enable **Write mode**.
8. Run flash.
9. Wait for completion, then power-cycle the radio if needed to see the new logo.

CLI-only equivalent:
1. `baofeng-logo-flasher ports`
2. `baofeng-logo-flasher upload-logo-serial ...` (dry run)
3. `baofeng-logo-flasher upload-logo-serial ... --write --confirm WRITE`

## 8) Safety notes

- Always run a dry run/simulation before a real write.
- Real writes require both `--write` and `--confirm WRITE` in CLI.
- Use a stable USB cable and avoid disconnecting during flashing.
- Double-check model selection before writing.
- For A5 models (`UV-5RM` / `UV-17` family), direct read-back is not implemented.

## 9) Troubleshooting

- `command not found`:
  - reinstall in active environment: `pip install -e .` or `pip install -e ".[ui]"`
- missing dependency errors:
  - install dependencies in your active venv.
- serial port issues:
  - run `baofeng-logo-flasher ports` and use full device path.
- write blocked:
  - include both `--write` and `--confirm WRITE`.
- UI seems stale:
  - `make stop` then `make start`.
- need deeper diagnostics:
  - run with `--debug-bytes` and inspect `out/logo_debug/manifest.json`.

## 10) Where to get help / report issues

- Check project docs:
  - `TROUBLESHOOTING.md`
  - `LOGO_PROTOCOL.md`
  - `docs/UI_BEHAVIOR.md`
- Report bugs or request features:
  - https://github.com/XoniBlue/Baofeng-Logo-Flasher/issues
