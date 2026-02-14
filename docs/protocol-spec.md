# Protocol Spec

This document consolidates protocol notes for supported models:
- UV-5RM / UV-17* family: A5-framed direct logo upload protocol
- DM-32UV: vendor PowerOnPicture.exe picture upload protocol

If you are looking for end-user usage instructions, see `docs/user-guide.md`.

## UV-5RM / UV-17* A5 Logo Upload (Direct Serial)

### Scope

Applies to models configured for A5 logo flashing in `src/baofeng_logo_flasher/core/boot_logo.py`.

Primary implementation files:
- `src/baofeng_logo_flasher/protocol/logo_protocol.py`
- `src/baofeng_logo_flasher/core/boot_logo.py`
- `src/baofeng_logo_flasher/core/actions.py`

### Critical Behavior (Addressing)

For tested UV-5RM/UV-17-family firmware, `CMD_WRITE (0x57)` addressing is chunk-indexed.

Working mode:
- address sequence: `0x0000`, `0x0001`, `0x0002`, ...
- payload length: `0x0400` bytes per write frame

Historical failing mode (fixed):
- address sequence: `0x0000`, `0x0400`, `0x0800`, ...
- symptom: top-line image fragment + gray/garbled rest of display

### Upload Sequence

```text
1) Handshake: PROGRAMBFNORMALU -> expect 0x06
2) Enter logo mode: 'D' (0x44)
3) Init frame: CMD 0x02 payload "PROGRAM"
4) Config frame: CMD 0x04 addr 0x4504 payload 00 00 0C 00 00 01
5) Setup frame: CMD 0x03 addr 0x0000 payload 00 00 0C 00
6) Data frames: CMD 0x57 len 0x0400 (40 frames for 40960-byte image)
7) Completion: CMD 0x06 payload "Over"
```

### Frame Format

```text
A5 | CMD | ADDR_H | ADDR_L | LEN_H | LEN_L | PAYLOAD... | CRC16_XMODEM (2 bytes, big-endian)
```

### Image Payload

- resolution: `160 x 128`
- bytes per pixel: `2`
- total bytes: `40960`
- pixel packing:
  - RGB/BGR565 16-bit words
  - serialized little-endian (`low byte`, then `high byte`)

### Debug Artifacts

CLI example:

```bash
baofeng-logo-flasher upload-logo-serial \
  --port /dev/cu.Plser \
  --in mylogo.png \
  --model UV-5RM \
  --write --confirm WRITE \
  --debug-bytes --debug-dir out/logo_debug
```

Expected artifacts include `manifest.json` plus byte-true payload/frame dumps.

## DM-32UV PowerOnPicture.exe Picture Upload

This is the protocol used by Baofeng’s Windows `PowerOnPicture.exe` tool.

### Serial Transport

- baudrate: typically 115200
- 8N1
- DTR=ON, RTS=ON
- short exchanges use ~500ms read windows; chunk ACK uses ~5000ms

### Picture BIN Format

Files contain an 8-byte header followed by RGB565 payload.
On-wire transfer skips the first 8 bytes.

Header layout (8 bytes):
- offset 0..1: `0x1000` (little-endian)
- offset 2..3: width (uint16 LE)
- offset 4..5: height (uint16 LE)
- offset 6: 0x00 (observed)
- offset 7: treat as 0

Payload:
- RGB565, little-endian 16-bit pixels
- row-major

For DM32 recommended dimensions:
- width=240, height=320
- payload_len = 240*320*2 = 153600 bytes

### Handshake / Preflight (ACK=0x06)

The vendor tool performs a sequence of probes before bulk transfer, including:
- ASCII `PSEARCH` -> read 8 bytes, success if first byte is `0x06`
- ASCII `PASSSTA` -> ACK check
- additional binary `V` and `G` commands and a fixed-length `S` read
- ASCII `PROGRAM` -> read 1 byte `0x06`

### Bulk Transfer: `W` Packets

Host -> Radio packet format:

```text
57               ; 'W'
addr0 addr1 addr2; 24-bit address, little-endian
lenLo lenHi      ; uint16 length, little-endian
data[len]        ; payload bytes
```

Chunking:
- max chunk size: 0x1000 bytes
- after each packet: expect single-byte ACK `0x06`

Addressing:
- tool computes `addr = base + offset` and serializes low/mid/high bytes
- implementation supports configurable `base_addr` (default 0)

Implementation:
- `src/baofeng_logo_flasher/protocol/dm32uv_picture_protocol.py`
- dispatch/config: `src/baofeng_logo_flasher/core/boot_logo.py`

## Notes From Previous Handoff (Firmware Flashing, Not Logo Upload)

Historical repo notes exist about vendor firmware flashing framing (`0xAA ... CRC ... 0xEF`) and an `UPDATE` handshake.
Those are firmware-upgrade specifics, not the A5 logo protocol and not the DM32UV PowerOnPicture picture protocol.

