# Baofeng Logo Flasher

Safety-first tooling for Baofeng boot logo workflows:
- inspect/scan clone images
- patch logos offline
- run direct serial logo operations (model/firmware dependent)
- use a CLI or Streamlit UI

## Project Status (as of February 8, 2026)

### What is working now

- CLI is fully wired and discoverable via `--help`.
- Core offline workflow is usable today:
  - `inspect-img`
  - `scan-bitmaps` / `scan-logo`
  - `patch-logo`
  - `verify-image`
- Safety gating is implemented for write operations:
  - `--write` required
  - confirmation token `WRITE` required (prompt or `--confirm WRITE`)
- Streamlit UI runs and exposes the major workflows.
- Local tests are passing in current environment:
- Direct serial logo flashing still depends on radio model + firmware behavior.
- Some UI patching behavior is less mature than CLI patching and needs alignment.
- No automated, real-hardware CI validation yet.

If you need highest reliability right now, prefer the offline patch workflow first.

## Repo Progress

### Completed

- CLI command surface for inspection, patching, and radio I/O.
- Shared safety layer (`core/safety.py`) used for write gating.
- Model capability reporting (`list-models`, `show-model-config`, `capabilities`).
- Bitmap scanning and preview export pipeline.
- Streamlit UI with tabs for flasher/capabilities/tools/verify.
- Test coverage for parsing, codec/patching logic, and key flow components.

### In progress

- Normalizing model/protocol definitions so all commands report the same truth.
- Tightening protocol certainty for UV-5RM/UV-17-family direct upload flows.
- Improving UI parity with CLI for patch configuration.

### Needs to be finished (priority order)

1. Unify model configuration sources.
- Remove duplicate/overlapping model definitions.
- Ensure protocol/magic/reporting is consistent in `list-models`, `show-model-config`, and `capabilities`.

2. Finish UI patch workflow parity.
- Make UI patching use the same offset/format/size controls and codec path as CLI `patch-logo`.
3. Expand hardware validation.
- Add repeatable hardware test matrix by model + firmware.
- Capture known-good/known-bad behavior per command (`download-logo`, `upload-logo`, `flash-logo`).

4. Add CI and quality gates.
- Run tests automatically on push/PR.
- Track regressions for parser/model/protocol metadata.

5. Finalize model support policy.
- Explicitly mark each model as `supported`, `experimental`, or `discovery only` in docs and command output.

## Requirements

- Python `3.9+`
- Core deps: `pyserial`, `pillow`, `rich`, `typer`
- Optional UI dep: `streamlit`

## Install

```bash
python3 -m venv venv
source venv/bin/activate
pip install -e .
```

With UI + dev extras:

```bash
pip install -e ".[ui,dev]"
```

## Quick Start

### CLI

```bash
baofeng-logo-flasher --help
```

### UI

```bash
```

Alternative:

```bash
streamlit run src/baofeng_logo_flasher/streamlit_ui.py
```

## Safety Model

Write-capable commands are blocked unless explicitly enabled.

### Required for writes

1. Pass `--write`
2. Confirm with token `WRITE`

Interactive terminal:
- You will be prompted to type `WRITE`.


```bash
baofeng-logo-flasher upload-logo \


### Device / model commands

- `list-devices`
- `list-models`
- `show-model-config <model>`
- `detect --port ...`
### Offline image commands

- `inspect-img <image.img>`
- `scan-bitmaps <image.img> [--max N] [--step N] [--output DIR]`
- `patch-logo <clone.img> <logo.png|jpg> --offset ... [--format ...] [--size WxH]`
- `verify-image <clone.img>`
### Radio commands
- `read-clone --port ... [--output file]`
- `download-logo --port ... [--out file] [--model ...] [--discover ...] [--raw]`
- `upload-logo --port ... --in ... [--model ...] [--discover ...] [--dry-run] [--write] [--confirm WRITE]`

baofeng-logo-flasher inspect-img clone.img
baofeng-logo-flasher scan-bitmaps clone.img
baofeng-logo-flasher patch-logo clone.img mylogo.png --offset 0x5A0 --format row_msb --size 128x64

### 2. Then attempt direct radio write only after verification

```bash
baofeng-logo-flasher upload-logo --port /dev/ttyUSB0 --in boot_logo.bmp --write
```

Current tabs:
- `Capabilities`
- `Tools & Inspect`
- `Verify & Patch`

Behavior:
- Global safety panel and write-mode controls.
- Simulation mode for flash-related workflows.
- Warning surface for risky operations.

## Testing

Run:

```bash
pytest tests/ -v
```

Current repo includes one manual integration test that is skipped by default (requires real radio).

## Documentation Index

- `DEVELOPMENT.md` - architecture and extension guidance
- `docs/UI_BEHAVIOR.md` - UI safety/confirmation behavior
- `docs/IMAGE_LAYOUT.md` - clone layout and logo discovery workflow
- `LOGO_PROTOCOL.md` - A5 protocol reference notes
- `TROUBLESHOOTING.md` - setup/runtime troubleshooting
