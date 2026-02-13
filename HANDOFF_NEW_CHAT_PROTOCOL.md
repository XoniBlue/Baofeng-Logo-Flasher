# Handoff: UV-5RM Firmware Flashing Protocol (Vendor EXE Decompiled)

This handoff captures the current state of the repo and what to do next to make serial firmware flashing protocol-correct and safer.

## Repo / Workspace

- Project: `/Users/xoni/Documents/GitHub/Baofeng_Logo_Flasher`
- Streamlit UI: `src/baofeng_logo_flasher/streamlit_ui.py`
- Firmware tooling: `src/baofeng_logo_flasher/firmware_tools.py`
- ILSpy work dir: `ilspy/`

## Key Reference (Read This First)

- `ilspy/PROTOCOL_FINDINGS.md`

This document contains the verified protocol details extracted from the vendor Windows flasher:
- Serial settings (115200, DTR/RTS enabled)
- Handshake (`PROGRAM` + `BFNORMAL` + `0x55`, ACK, `UPDATE`, ACK)
- Packet framing (`0xAA ... CRC16 ... 0xEF`)
- Command IDs and update flow (cmd 66, 1, 4, 3, 5, 3, 69)
- Retry/error codes

## What Was Verified vs Current Implementation

Verified (from vendor EXE decompile):
- Handshake candidate `PROGRAMBFNORMALU` is real.
- Protocol is CRC16-framed packets starting with `0xAA` and ending with `0xEF`.
- Transport is 1024-byte chunks and package counts; not per-chunk absolute addresses.

Current repo status:
- `LegacyFirmwareFlasher` in `src/baofeng_logo_flasher/firmware_tools.py` is **not protocol-correct** for vendor firmware upgrades (it uses a different frame structure and defaults).
- Streamlit UI has safety gating improvements already (expert unlock + `WRITE` confirmation), but it currently calls the legacy flasher.

## Immediate Goal For Next Chat

Replace/augment serial firmware flashing to use the vendor-protocol implementation, and keep the old one either removed or explicitly labeled as unsupported for UV-5RM upgrades.

## Implementation Plan (Concrete)

1. Add new protocol implementation (don’t modify the vendor dump logic):
   - New class in `src/baofeng_logo_flasher/firmware_tools.py`, e.g. `VendorFirmwareFlasher`.
   - Implement:
     - `crc16_ccitt(dat, offset, count, poly=0x1021, init=0)`
     - `pack_packet(cmd, cmdArgs, data)` -> bytes with `0xAA...0xEF`
     - `read_packet()` -> parse from serial stream, validate header/end and CRC
     - `handshake(model_tag=b"BFNORMAL")`:
       - write `b"PROGRAM" + model_tag + b"U"`, expect `0x06`
       - write `b"UPDATE"`, expect `0x06`
     - `send_bf(bf_bytes)`:
       - parse `.BF` header (16 bytes) and lengths
       - compute `ceil(len/1024)` counts
       - send cmd=66, cmd=1("BOOTLOADER"), cmd=4(count1), cmd=3 chunks, cmd=5(count2), cmd=3 chunks, cmd=69
       - implement retry on error code 226 (data check error)

2. Update Streamlit tabs to use new flasher:
   - Firmware Flash tab:
     - require `.BF` (vendor protocol is BF-package based) or explicitly wrap raw BIN to BF before flashing
   - Dumper serial flash:
     - if we continue supporting it, it should also use the vendor protocol for correctness

3. Keep safety defaults:
   - Simulation-only default
   - Expert unlock required for real writes
   - `WRITE` confirmation required

4. Tests:
   - New tests for CRC/pkt packing:
     - verify against known vectors (you can generate using `PackageFmt.cs` logic in Python)
   - Test BF header parsing -> package counts and chunk slicing

## Repro Commands (ILSpy)

The repo includes a working ILSpy CLI setup:

```bash
cd /Users/xoni/Documents/GitHub/Baofeng_Logo_Flasher
DOTNET_ROOT="$PWD/ilspy/dotnet8" ./ilspy/tools/ilspycmd -p -o ilspy/decompile/BF_Upgrade_Tool BF_Upgrade_Tool_for_TFT_330L_Series.exe
```

Decompiled code locations:
- `ilspy/decompile/BF_Upgrade_Tool/KDH_Bootloader/BootHelper.cs`
- `ilspy/decompile/BF_Upgrade_Tool/KDH_Bootloader/PackageFmt.cs`
- `ilspy/decompile/BF_Upgrade_Tool/KDH_Bootloader/FormMain.cs`

## Notes / Risks

- With only a K-plug and no SWD recovery, any protocol mistakes can brick the radio.
- The vendor EXE provides enough detail to implement the protocol correctly; do not guess framing.
- If further validation is needed, capture serial traffic with a virtual COM proxy (on Windows) and compare with the new implementation.

