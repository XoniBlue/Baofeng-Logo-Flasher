# Installation

## Requirements

- Python 3.9+
- Serial access to radio (USB data cable + OS driver/permission)

Declared in:
- `pyproject.toml` (`requires-python`, `dependencies`, `optional-dependencies`)

## macOS / Linux

```bash
git clone <repo-url>
cd Baofeng_Logo_Flasher
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[ui]"
```

## Windows (PowerShell)

```powershell
git clone <repo-url>
cd Baofeng_Logo_Flasher
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[ui]"
```

## Minimal CLI-only install

```bash
pip install -e .
```

UI requires optional extra `ui`.

## Verify Installation

```bash
baofeng-logo-flasher --help
baofeng-logo-flasher ports
```

Optional UI check:

```bash
baofeng-logo-flasher-ui
```

If missing Streamlit extras, the UI launcher exits with explicit install guidance.
Reference: `src/baofeng_logo_flasher/streamlit_ui.py` import guard.

## Permissions and Drivers

- macOS/Linux may require user membership in serial-access groups or appropriate `/dev/*` permissions.
- Windows requires COM-port visibility and correct USB-serial driver.

The app itself does not install drivers; it assumes OS-level serial device availability (`pyserial` usage in `protocol/uv5rm_transport.py` and `boot_logo.py`).

## Offline Considerations

- After dependencies are installed locally, runtime is local-only serial I/O.
- No network calls are implemented in runtime code paths.
