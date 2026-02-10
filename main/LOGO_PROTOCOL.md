# Logo Protocol Notes (A5 Serial)

Implementation notes for direct logo upload used in this repository.
For end-user instructions, see `README.md`.

## Scope

Applies to models configured for direct A5 flashing in `src/baofeng_logo_flasher/boot_logo.py`.

Primary implementation files:
- `src/baofeng_logo_flasher/protocol/logo_protocol.py`
- `src/baofeng_logo_flasher/boot_logo.py`
- `src/baofeng_logo_flasher/core/actions.py`

## Critical Behavior

For tested UV-5RM/UV-17-family firmware, `CMD_WRITE (0x57)` addressing is chunk-indexed.

Working mode:
- address sequence: `0x0000`, `0x0001`, `0x0002`, ...
- payload length: `0x0400` bytes per write frame


Historical failing mode (fixed):
- In older builds or with misconfiguration, address sequence: `0x0000`, `0x0400`, `0x0800`, ...
- This produced the symptom: top-line image fragment + gray/garbled rest of display.
- This issue affected previous versions or incorrect address mode settings, and is resolved in current releases with correct configuration.

Configured defaults use `write_addr_mode: "chunk"` for supported UV-5RM/UV-17 entries.

## Upload Sequence

```text
1) Handshake: PROGRAMBFNORMALU -> expect 0x06
2) Enter logo mode: 'D' (0x44)
3) Init frame: CMD 0x02 payload "PROGRAM"
4) Config frame: CMD 0x04 addr 0x4504 payload 00 00 0C 00 00 01
5) Setup frame: CMD 0x03 addr 0x0000 payload 00 00 0C 00
6) Data frames: CMD 0x57 len 0x0400 (40 frames for 40960-byte image)
7) Completion: CMD 0x06 payload "Over"
```

## Frame Format

```text
A5 | CMD | ADDR_H | ADDR_L | LEN_H | LEN_L | PAYLOAD... | CRC16_XMODEM (2 bytes, big-endian)
```

## Image Payload

- resolution: `160 x 128`
- bytes per pixel: `2`
- total bytes: `40960`
- pixel packing in implementation:
  - BGR565 in 16-bit word (`BBBBBGGGGGGRRRRR`)
  - serialized little-endian (`low byte`, then `high byte`)

## Debug Artifacts

Use CLI debug mode to export exact bytes sent:

```bash
baofeng-logo-flasher upload-logo-serial \
  --port /dev/cu.Plser \
  --in mylogo.png \
  --model UV-5RM \
  --write --confirm WRITE \
  --debug-bytes --debug-dir out/logo_debug
```

Expected artifacts:
- `image_payload.bin`
- `write_payload_stream.bin`
- `write_frames.bin`
- `preview_row_major.png`
- `manifest.json`

## Caveat on External Captures

Do not assume third-party pcaps are complete unless they include handshake, control, data, and completion continuity for a full session.
