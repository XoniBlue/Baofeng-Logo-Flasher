# Troubleshooting

Quick fixes for common runtime problems. For setup and normal usage, see `README.md`.

## 1. Dependency errors

If imports fail, install package dependencies in the active environment:

```bash
pip install -e .
```

For Streamlit UI:

```bash
pip install -e ".[ui]"
```

## 2. CLI command not found

Install the package in your current environment:

```bash
pip install -e .
```

Or run directly as a module:

```bash
PYTHONPATH=src python -m baofeng_logo_flasher.cli --help
```

## 3. Serial port errors

List ports first:

```bash
baofeng-logo-flasher ports
```

Use the full path, for example `/dev/cu.Plser`.

## 4. Flash reports success but display shows top line + gray screen

This symptom is strongly tied to incorrect write addressing mode.

Expected for UV-5RM/UV-17 A5 flashing:
- `write_addr_mode: chunk`

Checks:
1. Pull latest code.
2. Fully restart Streamlit if using UI.
3. Validate once with CLI:

```bash
baofeng-logo-flasher upload-logo-serial \
  --port /dev/cu.Plser \
  --in my_logo.png \
  --model UV-5RM \
  --write --confirm WRITE
```

## 5. Verify exact transmitted bytes

```bash
baofeng-logo-flasher upload-logo-serial \
  --port /dev/cu.Plser \
  --in my_logo.png \
  --model UV-5RM \
  --write --confirm WRITE \
  --debug-bytes --debug-dir out/logo_debug
```

Inspect `out/logo_debug/manifest.json` for:
- `address_mode` should be `chunk`
- `image_bytes` should be `40960`
- `frame_count` should be `40`

## 6. Streamlit behaves like stale code

- stop Streamlit
- restart Streamlit
- re-run flash
- if needed, enable debug-bytes and inspect `out/streamlit_logo_debug/manifest.json`

## 7. Write blocked

Write operations require both:
- `--write`
- confirmation token `WRITE`

## 8. Backup/read-back expectations for A5 models

For UV-5RM/UV-17 A5 models, direct logo read-back is not implemented in this repo.
Use backup options provided by your workflow before writing.

## 9. Run tests

```bash
pytest tests/ -v
```
