# A5 Logo Protocol Reference (UV-5RM / UV-17 Family)

Technical reference for the direct logo upload flow implemented in this project.

Use this document as a protocol note, not as a guarantee that every firmware variant accepts the same sequence.

## Scope

Applies to the A5-framed boot logo upload workflow used for models configured with:
- Handshake: `PROGRAMBFNORMALU`
- Baud: `115200`
- Payload format: `RGB565` (`160x128`)

Related code:
- `src/baofeng_logo_flasher/boot_logo.py`
- `src/baofeng_logo_flasher/protocol/logo_protocol.py`
- `src/baofeng_logo_flasher/core/actions.py`

## Transport Settings

- Serial: `115200`, `8N1`
- Timeout: model/config dependent
- Handshake ACK expected: `0x06`

## High-Level Upload Sequence

```text
1) Send handshake: PROGRAMBFNORMALU (16 bytes)
   Expect: 06

2) Send mode byte: 44 ('D')
   Expect: (none or device-specific)

3) Send init frame (cmd 0x02, payload "PROGRAM")
   Expect: A5 ... 59 ...  (Y/ack payload)

4) Send config frame (cmd 0x04, addr 0x4504)
   Expect: A5 ... 59 ...

5) Send setup frame (cmd 0x03)
   Expect: A5 ... 59 ...

6) Send image chunks (cmd 0x57, ~1004-byte payload chunks)
   Expect: A5 EE ... 04 ... (data ack)

7) Send completion frame (cmd 0x06, payload "Over")
   Expect: 00 (or model-specific completion)
```

## A5 Frame Layout

```text
A5 | CMD | ADDR_H | ADDR_L | LEN_H | LEN_L | PAYLOAD... | CHECKSUM(2B)
```

Fields are represented in captured traffic as command/address/length followed by payload and trailing checksum bytes.

## Captured Example Frames

Handshake:

```text
TX: 50 52 4F 47 52 41 4D 42 46 4E 4F 52 4D 41 4C 55
RX: 06
TX: 44
```

Init (`0x02`):

```text
TX: A5 02 00 00 00 07 50 52 4F 47 52 41 4D 0C AB
RX: A5 02 00 00 00 01 59 73 AD
```

Config (`0x04`, addr `0x4504`):

```text
TX: A5 04 45 04 00 06 00 00 0C 00 00 01 83 F4
RX: A5 04 45 04 00 01 59 06 82
```

Setup (`0x03`):

```text
TX: A5 03 00 00 00 04 00 00 0C 00 E1 2F
RX: A5 03 00 00 00 01 59 36 0D
```

Data (`0x57`) and ACK (`0xEE`):

```text
TX: A5 57 [addr_hi] [addr_lo] 04 00 [payload...] [chk...]
RX: A5 EE 00 00 00 01 04 78 2E
```

Completion (`0x06`):

```text
TX: A5 06 00 00 00 04 4F 76 65 72 A9 5E
RX: 00
```

## Image Format Constraints

- Resolution: `160x128`
- Pixel format: `RGB565`
- Byte order: little-endian per pixel
- Raw payload size: `160 * 128 * 2 = 40,960 bytes`

## Address Notes

Observed addresses in traffic:
- `0x0000`: image data base
- `0x4504`: config/metadata frame target

These values are from capture-based behavior and may vary by firmware.

## Checksum Notes

Frame checksums are present as trailing bytes in captures. Exact algorithm details can vary by implementation path and should be confirmed in code/tests for any new model integration.

## Read Path Note

Some toolchains use a read mode (`'R'`) variant, but practical read support is model/firmware dependent and should be treated separately from upload support.

## Practical Guidance

1. Treat protocol support as model + firmware specific.
2. Test in simulation/dry-run flow first.
3. Keep write-gating enabled (`--write` + `WRITE` confirmation).
4. Use `capabilities` and model config commands before attempting direct upload.
