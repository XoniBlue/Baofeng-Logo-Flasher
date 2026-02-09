# Usage Guide

## Entrypoints

- CLI: `baofeng-logo-flasher`
- UI: `baofeng-logo-flasher-ui`

Defined in `pyproject.toml`.

## Common Tasks

### 1) Discover serial ports

```bash
baofeng-logo-flasher ports
```

Good output:
- table with `Port`, `Device`, `Description`.

Failure output:
- `pyserial not installed: pip install pyserial`

### 2) List supported model profiles

```bash
baofeng-logo-flasher list-models
```

Shows serial flash models and clone-based model config tables.

### 3) Detect connected radio

```bash
baofeng-logo-flasher detect --port /dev/ttyUSB0
```

Good output:
- `Radio Identification` table with model, firmware, ident bytes.

Failure output:
- `Detect failed: ...`

### 4) Simulate A5 serial logo upload (safe dry run)

```bash
baofeng-logo-flasher upload-logo-serial \
  --port /dev/ttyUSB0 \
  --in my_logo.png \
  --model UV-5RM \
  --dry-run
```

Good output:
- success message indicating simulation only.

Failure output examples:
- model not in `SERIAL_FLASH_CONFIGS`
- invalid `--write-addr-mode`
- image path missing

### 5) Real A5 serial logo upload

```bash
baofeng-logo-flasher upload-logo-serial \
  --port /dev/ttyUSB0 \
  --in my_logo.png \
  --model UV-5RM \
  --write --confirm WRITE
```

Good output:
- `Serial upload complete` (or protocol completion message)

Failure output examples:
- handshake/ACK failure from `logo_protocol.py`
- write permission denial from `core/safety.py`

### 6) UI workflow

```bash
baofeng-logo-flasher-ui
```

Then in browser:
1. Step 1 connection (model + port)
2. Step 2 upload image (auto converted to model size)
3. Step 3 run simulate or write mode flash

## Advanced Tasks

### Debug protocol payloads

CLI:

```bash
baofeng-logo-flasher upload-logo-serial \
  --port /dev/ttyUSB0 --in logo.bmp --model UV-5RM \
  --write --confirm WRITE \
  --debug-bytes --debug-dir out/logo_debug
```

Generated artifacts are written by `protocol/logo_protocol.py:dump_logo_debug_artifacts`.

### Legacy path with explicit region

```bash
baofeng-logo-flasher upload-logo \
  --port /dev/ttyUSB0 --in logo.bmp \
  --logo-start 0x1000 --logo-length 61440 \
  --write --confirm WRITE
```

## Safety Expectations

- Any non-simulated write requires explicit confirmation gates.
- Prefer dry-run/simulation before live write.
- Keep stable power/cable during write operations.
