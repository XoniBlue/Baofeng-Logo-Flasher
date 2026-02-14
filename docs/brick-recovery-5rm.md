# UV-5RM Brick Recovery Notes (Serial Dumper Helper Flash)

Date: 2026-02-13

This file is a handoff for recovering a Baofeng UV-5RM after attempting to flash the "bootloader dumper helper" firmware over the K-plug serial link.

## What Happened

1. A vendor-protocol serial flasher was implemented based on ILSpy decompilation of Baofeng's Windows flasher EXE.
2. Dry-run probing was used to validate:
   - raw handshake: `PROGRAM` + model tag + `0x55` (`'U'`) -> `0x06` ACK; then `UPDATE` -> `0x06` ACK
   - framed packets: `0xAA ... CRC16 ... 0xEF` responses to `cmd=66` and `cmd=1 ("BOOTLOADER")`
3. A real write-run was then used to flash the dumper helper firmware (a wrapped `.BF`) via the vendor framing protocol.
4. After that write, the radio stopped booting normally (no display / appears dead).

## Observed Symptoms After the Failed Flash

- Radio does not power on normally (no UI).
- Dumper UART monitor shows no output.
- Vendor firmware flasher cannot even "probe":
  - Raw handshake fails: `Read timeout waiting for radio response`
  - Framed probe fails: cannot find packet start byte `0xAA` (no framed replies).

Example CLI log (framed-only probe):
- Retries for `cmd=66` time out waiting for packet start `0xAA`
- Fallback to `cmd=1` also times out / never sees `0xAA`

## What This Means

This looks like a soft-brick where:

- The application flash region likely contains invalid code (or the wrong image for this specific hardware/variant).
- The UART update/bootloader entry path is not responding anymore (at least not to the known vendor protocol).

At this point, reliable recovery is expected to require **SWD** access to the MCU (AT32F421 family in this project).

## Immediate "Do Not" List

- Do not keep attempting random serial flashing while the device is non-responsive.
- Do not assume that "dry-run" is harmless: framed probes can still push the device into boot/update state.
- Do not flash bootloader (`0x08000000`) images unless you have the exact correct bootloader for this hardware.

## Next Steps (SWD Recovery Plan)

### What You Need

- SWD probe: ST-Link V2 (cheap), J-Link, or compatible.
- Wire + ideally a fine-tip soldering iron (the SWD pads are usually small).
- Software: `pyocd` is the easiest starting point on macOS.

### What You’ll Do (High Level)

1. Open the radio and locate pads/signals:
   - `GND`, `3V3`, `SWDIO`, `SWCLK` (optionally `NRST` / reset)
2. Connect the probe.
3. Confirm the probe can see the MCU.
4. Mass erase or erase the application region.
5. Program a known-good firmware to the application base used by this project:
   - `FW_FLASH_BASE = 0x08001000`

### Getting a Known-Good Firmware Image

This repo includes factory `.BF` files under:
- `firmware_tools/factory_firmware/`

You must unwrap/decrypt the `.BF` to a raw `.bin` before flashing over SWD.

If you have a factory BF (example path):
- `firmware_tools/factory_firmware/<SOME_FACTORY>.BF`

Use Python to extract firmware bytes to a `.bin`:

```bash
cd /Users/xoni/Documents/GitHub/Baofeng_Logo_Flasher
./.venv/bin/python - <<'PY'
from pathlib import Path
from baofeng_logo_flasher.firmware_tools import unwrap_bf_bytes

bf_path = Path("firmware_tools/factory_firmware/REPLACE_ME.BF")
out_bin = Path("out/recovery_firmware.bin")
out_bin.parent.mkdir(parents=True, exist_ok=True)

fw, _data, hdr = unwrap_bf_bytes(bf_path.read_bytes(), decrypt_firmware=True, decrypt_data=False)
out_bin.write_bytes(fw)
print("BF header:", hdr)
print("Wrote:", out_bin, "bytes=", len(fw))
PY
```

### Flashing via pyOCD (Sketch)

Assuming target `at32f421x8` and you produced `out/recovery_firmware.bin`:

```bash
pyocd erase --chip -t at32f421x8
pyocd flash -t at32f421x8 --base-address 0x08001000 out/recovery_firmware.bin
```

Notes:
- If `pyocd` can’t connect, you may need `NRST` wired, or you may need to hold/reset timing.
- Some probes/targets require OpenOCD instead of pyOCD.

## Files And Code Relevant To This Incident

- Vendor protocol implementation (Python):
  - `src/baofeng_logo_flasher/firmware_tools.py`
  - `tests/test_vendor_protocol.py`
- Streamlit/CLI integration:
  - `src/baofeng_logo_flasher/streamlit_ui.py`
  - `src/baofeng_logo_flasher/cli.py`
- Reverse engineering notes:
  - `ilspy/PROTOCOL_FINDINGS.md`

## TODO When You Come Back With Hardware

1. Photograph PCB and identify SWD pads.
2. Confirm MCU can be read via SWD.
3. Extract a correct factory firmware for UV-5RM variant.
4. Flash firmware to `0x08001000` via SWD.
5. Only after normal boot is restored:
   - re-evaluate dumper helper approach
   - capture a serial trace of the vendor flasher on Windows if possible

