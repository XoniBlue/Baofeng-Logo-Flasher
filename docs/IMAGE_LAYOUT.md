# Image Layout and Logo Discovery

This document describes how to locate and patch logo data in clone images using the current tooling.


- The app supports offline clone inspection and patching.
- `scan-bitmaps` and `scan-logo` can generate logo candidates and previews.

- Logo offset/address
- Bitmap dimensions
- Bitmap packing format (`row_msb`, `row_lsb`, `page_msb`, `page_lsb`)


### 1. Inspect clone image

baofeng-logo-flasher inspect-img clone.img
```

### 2. Scan for candidates

Either command is available:

```bash
baofeng-logo-flasher scan-bitmaps clone.img
```

or

```bash
baofeng-logo-flasher scan-logo clone.img
```

`scan-bitmaps` supports CLI tuning (`--max`, `--step`, `--output`).

### 3. Review previews

Open generated previews from `out/previews/` and identify likely logo regions.

### 4. Patch offline

```bash
baofeng-logo-flasher patch-logo clone.img mylogo.png \
  --offset 0x5A0 \
  --format row_msb \
  --size 128x64
```

### 5. Verify image

```bash
baofeng-logo-flasher verify-image clone.img
```

## Notes on Safety

- Offline patching creates backups through patching utilities.
- Radio writes are separate operations and remain write-gated (`--write` + confirmation).

## Recording Confirmed Mappings

When you confirm a working mapping, record:
- Radio model
- Firmware/version identifier
- Offset
- Format
- Dimensions
- Any caveats (reboot needed, secondary logo region, etc.)

Keeping this list current is the fastest way to reduce trial-and-error on future devices.
