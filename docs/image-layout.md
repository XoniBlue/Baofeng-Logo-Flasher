# Image Layout Notes

This project now uses direct A5 serial logo upload as the primary and supported path for
UV-5RM/UV-17-family radios.

Used by:
- CLI `upload-logo-serial`
- Streamlit `Boot Logo Flasher` tab

This workflow sends `160x128 RGB565` pixel payload.

## Confirmed A5 Layout Finding

For tested UV-5RM firmware, successful A5 writes require:
- chunk payload size: `1024`
- `CMD_WRITE` address mode: `chunk` (0,1,2,...)


Using byte-offset address mode (historical symptom, older versions):
- recognizable content only on top row
- remaining display gray/garbled

## Offline Clone/Patch Workflows

Offline clone-image inspection/scan/patch workflows are not part of the active product path in
this repository release.

## Direct A5 Upload Example

```bash
PYTHONPATH=src python -m baofeng_logo_flasher.cli upload-logo-serial \
  --port /dev/cu.Plser \
  --in mylogo.png \
  --model UV-5RM \
  --write --confirm WRITE
```

## Record Confirmed Mappings

When validating a device, record:
- model
- firmware/version string
- workflow used (A5 serial)
- required protocol caveats (address mode, chunk size)
