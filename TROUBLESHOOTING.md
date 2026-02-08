# Troubleshooting

## 1. CLI import or dependency errors

### `ImportError: PySerial required`

Install project dependencies in the active environment:

```bash
pip install -e .
```

For UI usage:

```bash
pip install -e ".[ui]"
```

## 2. Command not found (`baofeng-logo-flasher`)

You likely have not installed the package in your current environment.

```bash
pip install -e .
```

Or run via module in a configured env:

```bash
PYTHONPATH=src python3 -m baofeng_logo_flasher.cli --help
```

## 3. No serial ports listed

Check ports:

```bash
baofeng-logo-flasher ports
```

If none appear:
- Verify cable/adapter and USB permissions
- Close apps that may hold the port (CHIRP, terminal serial monitors)
- Reconnect device and re-run `ports`

## 4. Radio detection/read failures

Try in order:
1. Validate the port path with `ports`
2. Run `detect --port ...`
3. Run `read-clone --port ...` to confirm baseline communication
4. Compare behavior with CHIRP on the same cable/port

If CHIRP works and this tool does not, capture the exact CLI error output and model/firmware details before adjusting protocol assumptions.

## 5. Write blocked unexpectedly

Write commands intentionally fail unless safety requirements are met.

Required for writes:
- `--write`
- confirmation token `WRITE` (interactive prompt or `--confirm WRITE`)

For scripts/non-interactive shells, include both flags explicitly.

## 6. Image patch errors

### Invalid offset/format/size

Use exact forms:
- Offset: decimal (`4096`), hex (`0x1000`), or suffix (`1000h`)
- Format: `row_msb`, `row_lsb`, `page_msb`, `page_lsb`
- Size: `WxH` (example `128x64`)

### Candidate region unknown

Run discovery first:

```bash
baofeng-logo-flasher scan-bitmaps clone.img
```

Review previews before patching.

## 7. UI does not start

Install UI extra and launch again:

```bash
pip install -e ".[ui]"
baofeng-logo-flasher-ui
```

## 8. Run tests to verify environment

```bash
pytest tests/ -v
```

If tests fail because dependencies are missing, reinstall in a fresh virtual environment.
