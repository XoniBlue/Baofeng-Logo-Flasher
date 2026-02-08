# Image Layout and Discovery Notes

This document covers clone-image bitmap discovery and how it differs from direct A5 serial logo upload.

## Two Different Workflows

### 1) Clone/offline bitmap workflows

Used by commands such as:
- `scan-bitmaps`
- `scan-logo`
- `patch-logo`
- `flash-logo` (clone patch/upload path)

These workflows involve monochrome bitmap layouts (`row_msb`, `row_lsb`, `page_msb`, `page_lsb`) and clone offsets.

### 2) Direct A5 serial logo upload (UV-5RM/UV-17)

Used by:
- CLI `upload-logo-serial`
- Streamlit Boot Logo Flasher tab

This workflow sends `160x128 RGB565` pixel payload, not monochrome clone bitmap formats.

## Confirmed A5 Layout Finding

For tested UV-5RM firmware, successful A5 writes require:
- chunk payload size: `1024`
- `CMD_WRITE` address mode: `chunk` (0,1,2,...)

Using byte-offset address mode can produce:
- recognizable content only on top row
- remaining display gray/garbled

## Clone Discovery Steps (offline)

1. Inspect clone image:

```bash
baofeng-logo-flasher inspect-img clone.img
```

2. Scan for candidates:

```bash
baofeng-logo-flasher scan-bitmaps clone.img
```

3. Review previews in `out/previews/`
4. Patch with confirmed offset/format:

```bash
baofeng-logo-flasher patch-logo clone.img mylogo.png \
  --offset 0x5A0 \
  --format row_msb \
  --size 128x64
```

5. Verify image:

```bash
baofeng-logo-flasher verify-image clone.img
```

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
- workflow used (clone vs A5)
- any required protocol caveats (address mode, chunk size)
