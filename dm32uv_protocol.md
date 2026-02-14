# dm32uv_protocol.m
#
# Reverse-engineered protocol + file format notes for:
#   Baofeng DM-32UV "PowerOnPicture.exe" (Boot Image Download tool)
#
# Source binary analyzed:
#   dev/Baofeng_DM-32UV_Picture_Tool/PowerOnPicture.exe
#
# Notes:
# - This EXE is native (MFC), not .NET; ILSpy won't decompile it.
# - Findings below come from static analysis (radare2) + string/import inspection.
#
# -----------------------------------------------------------------------------
# 1) Serial Transport
# -----------------------------------------------------------------------------
#
# Port selection:
#   Uses "COM%d" for COM1..COM9, and "\\\\.\\COM%d" for COM10+.
#   (see fcn.00407b50)
#
# Serial config:
#   - baudrate: configurable; default in lang.bf: 115200
#   - 8 data bits, no parity, 1 stop bit (8N1)
#   - DTR = ON, RTS = ON (EscapeCommFunction SETDTR=5, SETRTS=3)
#   - SetupComm(in=0xE10, out=0xE10) (3600 bytes)
#   - Reads are looped with a GetTickCount timeout; typical caller timeouts:
#       500ms for short exchanges, 5000ms for chunk ACK.
#
# -----------------------------------------------------------------------------
# 2) DM32UV Picture BIN Format
# -----------------------------------------------------------------------------
#
# The EXE maintains a single global buffer pointer + length:
#   - buffer base: 0x5ab71c (points to allocated memory)
#   - total length: 0x5ab718 (includes an 8-byte header)
#
# When transmitting the image to the radio, it sends ONLY the payload:
#   payload = buffer[8 : total_len]
# I.e. the first 8 bytes are a header used locally / in .BIN files, but skipped
# on-wire. (see fcn.004028a0, where it adds +8 before memcpy and subtracts 8
# from total for transmit loop)
#
# Header layout (8 bytes) (see fcn.004055d0, around 0x00405e4e):
#   offset 0..1: 0x1000 (little-endian) => bytes [0]=0x00, [1]=0x10
#   offset 2..3: width  (uint16 little-endian)
#   offset 4..5: height (uint16 little-endian)
#   offset 6:    0x00 (observed)
#   offset 7:    (not explicitly observed set in the snippet; treat as 0)
#
# Pixel payload (offset 8..):
#   - 16-bit RGB565, little-endian (low byte first)
#   - row-major
#
# Evidence:
#   - fcn.004055d0 writes pixel values into [buffer + 8 + 2*i] and [..+1]
#     (see 0x00405dfd/0x00405e04 store to +8/+9 etc)
#   - fcn.00402300 renders the buffer by reading little-endian 16-bit pixels and
#     expanding to COLORREF for SetPixel (RGB565 bit slicing).
#
# For DM32, recommended dimensions (from Readme.txt and dialog defaults):
#   width=240, height=320
#
# Expected total_len for 240x320 RGB565:
#   total_len = 8 + 240*320*2 = 153608 bytes (0x25808)
#   payload_len = total_len - 8 = 153600 bytes (0x25800)
#
# -----------------------------------------------------------------------------
# 3) On-Wire Protocol (COM)
# -----------------------------------------------------------------------------
#
# This is the "Download Image" protocol used by PowerOnPicture.exe.
#
# 3.1) Handshake / preflight (ACK byte is 0x06)
#
# The EXE performs a sequence of ASCII probes and small binary commands.
# Most steps are validated by observing 0x06 in the response buffer.
#
# Step A: PSEARCH
#   Host -> Radio: ASCII "PSEARCH" (7 bytes)
#   Radio -> Host: read 8 bytes; success if first byte == 0x06
#   Retries up to 5 times (500ms read windows).
#
# Step B: PASSSTA
#   Host -> Radio: ASCII "PASSSTA" (7 bytes)
#   Radio -> Host: similar ACK check for 0x06
#
# Step C: V commands (variable-length response)
#   Host -> Radio: 5 bytes: 56 00 00 40 0D
#   Radio -> Host:
#     - read 3 bytes, validate byte0 == 0x56
#     - let N = byte2
#     - read N bytes
#
#   Host -> Radio: 5 bytes: 56 00 00 00 0E
#   Radio -> Host: same 3-byte header + N-byte body behavior
#
# Step D: G command
#   Host -> Radio: 6 bytes: 47 00 00 00 00 01
#   Radio -> Host: if write succeeds, proceed
#
# Step E: S block read (0x106 bytes)
#   Radio -> Host: read exactly 0x106 bytes; validate first byte == 'S' (0x53)
#
# Step F: marker
#   Host -> Radio: 5 bytes: FF FF FF FF 0C
#
# Step G: enter PROGRAM
#   Host -> Radio: ASCII "PROGRAM" (7 bytes)
#   Radio -> Host: read 1 byte == 0x06
#
# Additional small single-byte exchanges occur (0x02, 0x06, and an 8-byte read
# appears in the code path), but the core data path is below.
#
# 3.2) Bulk transfer: 'W' packets (main flash/write loop)
#
# Packet format (Host -> Radio), built in fcn.004028a0 around 0x00403533:
#   57               ; 'W'
#   addr0 addr1 addr2; 24-bit address, little-endian
#   lenLo lenHi      ; uint16 length, little-endian
#   data[len]        ; payload bytes
#
# Chunking:
#   - Max chunk size: 0x1000 bytes (4096)
#   - Payload source: buffer[8:] (strip 8-byte BIN header)
#   - After each packet: Radio -> Host: 1 byte == 0x06 ACK
#     Timeout used: 0x1388 ms (5000ms).
#
# Addressing:
#   The EXE computes addr = (base + offset) and then serializes it as 3 bytes:
#     addr0 = addr & 0xFF
#     addr1 = (addr >> 8) & 0xFF
#     addr2 = (addr >> 16) & 0xFF
#
#   The exact 'base' value feeding this calculation was not conclusively located
#   in this pass (the 'W' block reads it from a local at [esp+0x30]).
#   Practical implementation should support configuring base_addr (default 0).
#
# -----------------------------------------------------------------------------
# 4) Useful Function / Address References (PowerOnPicture.exe)
# -----------------------------------------------------------------------------
#
# Serial open/config:
#   - fcn.00407b50: CreateFileA("COM%d"/"\\\\.\\COM%d"), SetCommState, SetupComm,
#     EscapeCommFunction(DTR/RTS), SetCommTimeouts, FlushFileBuffers.
#
# Serial write helper:
#   - fcn.00407cd0: WriteFile(h, buf, n)
#
# Serial read helper (loop until n or timeout):
#   - fcn.00407d10: ReadFile loop, uses ClearCommError + GetTickCount timeout.
#
# Download Image main routine:
#   - fcn.004028a0: handshake + W-packet loop.
#
# BIN header/pixel packer (image -> RGB565 BIN buffer):
#   - fcn.004055d0: fills header (0x1000, width, height, flags) and writes
#     RGB565 pixels to buffer[8:].
#
# BIN renderer (draw preview from buffer):
#   - fcn.00402300: reads header + RGB565 payload and renders via SetPixel.
#
