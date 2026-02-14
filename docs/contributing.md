# Contributing

This project is a Python tool with:
- a Typer CLI (`baofeng-logo-flasher`)
- a Streamlit UI (`baofeng-logo-flasher-ui`)

The `dev` branch is the canonical Python implementation. Do not merge JS/web logic from `web-dev` into this branch.

## Repository Map

- Quick start and end-user overview: `README.md`
- User guide (install + usage): `docs/user-guide.md`
- Protocol spec (A5 logo + DM32UV picture tool): `docs/protocol-spec.md`
- Architecture: `docs/architecture.md`
- UI behavior notes: `docs/ui-behavior.md`
- Image layout notes: `docs/image-layout.md`

## Runtime Entry Points

Entrypoints are defined in `pyproject.toml`:
- CLI: `baofeng_logo_flasher.cli:main`
- UI: `baofeng_logo_flasher.streamlit_ui:launch`

Implementation lives under:
- `src/baofeng_logo_flasher/ui/cli.py`
- `src/baofeng_logo_flasher/ui/streamlit_ui.py`

The legacy import paths are kept as thin compatibility wrappers.

## Architecture Notes (High Level)

Layers (top to bottom):
- `ui/`: CLI and Streamlit UI
- `core/`: shared workflows and safety gate
- `protocol/`: timing-sensitive serial/protocol logic
- `utils/`: pure helpers (image/codecs, BF wrapping helpers, crypto)
- `models/`: model registry and capability metadata

## Development Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[ui,dev]"
```

## Tests

```bash
pytest -q
```

## Safety Contract (Do Not Bypass)

Real writes must be gated by `core/safety.py:require_write_permission`.

The CLI and UI both enforce:
- simulation/dry-run defaults
- explicit write enablement
- confirmation token `WRITE` for non-interactive workflows

## Debugging

- CLI: enable byte dumps with `--debug-bytes --debug-dir ...` on serial upload commands.
- UI: enable debug-bytes option (writes to `out/streamlit_logo_debug`).

## Change Rule

When command behavior or protocol defaults change, update:
- `README.md` (Quick Start)
- `docs/user-guide.md`
- `docs/protocol-spec.md`
- `docs/troubleshooting.md`
- `docs/architecture.md`

