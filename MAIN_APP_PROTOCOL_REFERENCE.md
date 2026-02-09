# Main App Protocol Reference for `v2/web`

This document captures protocol/transport/safety behavior in the Python `main` app that `v2/web` must match for compatible A5 logo flashing.

## 1) Source-of-Truth File Inventory (Main App)

| Area | File | Why it is source-of-truth |
|---|---|---|
| A5 wire protocol constants + framing + CRC + upload sequence | `src/baofeng_logo_flasher/protocol/logo_protocol.py:34` | Defines opcodes, frame layout, CRC16-XMODEM, chunking, ACK acceptance, retry boundaries, and full upload workflow. |
| A5 model-to-config normalization | `src/baofeng_logo_flasher/boot_logo.py:28` | Builds `SERIAL_FLASH_CONFIGS` from registry and hard-sets `protocol=a5_logo`, `write_addr_mode=chunk`, `chunk_size=1024`, `pixel_order=rgb`, handshake bytes. |
| A5 identity probe path | `src/baofeng_logo_flasher/boot_logo.py:86` | `read_radio_id` performs read-only handshake/ident and enforces protocol family. |
| Flash entrypoint used by core/UI | `src/baofeng_logo_flasher/boot_logo.py:183` | `flash_logo` rejects non-A5 configs and dispatches to protocol uploader. |
| Shared write safety gate | `src/baofeng_logo_flasher/core/safety.py:88` | `require_write_permission` is the single allow/deny gate for writes. |
| Shared flash action wrapper + result object | `src/baofeng_logo_flasher/core/actions.py:105` | Wraps flashing with safety, logging capture, and `OperationResult`. |
| Streamlit safety/probe integration | `src/baofeng_logo_flasher/streamlit_ui.py:629` | Non-destructive probe + auto-select logic and core-flash invocation. |
| CLI safety and A5 command path | `src/baofeng_logo_flasher/cli.py:545` | `upload-logo-serial` command wiring, confirmation, address-mode override. |
| Model registry protocol parameters | `src/baofeng_logo_flasher/models/registry.py:33` | Canonical protocol/model metadata (`UV17PRO`, magic, timeout, logo dimensions). |
| Protocol package export surface | `src/baofeng_logo_flasher/protocol/__init__.py:1` | Public API boundary for protocol modules. |
| Legacy clone transport/protocol (non-A5) | `src/baofeng_logo_flasher/protocol/uv5rm_transport.py:42` | Separate protocol family; useful to avoid accidental mixing with A5 behavior. |
| Legacy clone protocol behavior | `src/baofeng_logo_flasher/protocol/uv5rm_protocol.py:54` | Clone identify/read/write/verify logic (different from A5). |

Supporting protocol notes:
- `LOGO_PROTOCOL.md:31` documents expected A5 sequence and chunk-address behavior.

## 2) End-to-End Protocol Flow (A5 Logo Upload)

### 2.1 Handshake / setup

Ordered pre-write sequence in `LogoUploader.upload_logo`:
1. Open serial, set DTR/RTS high, clear buffers (`logo_protocol.py:377`).
2. Handshake magic `PROGRAMBFNORMALU`, expect `0x06` (`logo_protocol.py:429`).
3. Enter logo mode: send `0x44` (`'D'`), no response expected (`logo_protocol.py:448`).
4. Send init frame (`CMD_INIT=0x02`) payload `PROGRAM`; expect ACK frame (`logo_protocol.py:460`).
5. Send config frame (`CMD_CONFIG=0x04`, addr `0x4504`, payload `00 00 0C 00 00 01`) (`logo_protocol.py:484`).
6. Send setup frame (`CMD_SETUP=0x03`, addr `0x0000`, payload `00 00 0C 00`) (`logo_protocol.py:506`).

Pre-write retries:
- Retries only steps above (not chunk writes), with `PREWRITE_MAX_ATTEMPTS=2`, delay `0.2s` (`logo_protocol.py:59`, `logo_protocol.py:671`).

### 2.2 Identity/model detection

A5 identity probe path:
- `read_radio_id` enforces `protocol == uv17pro` (`boot_logo.py:107`).
- Sends A5 magic, checks fingerprint prefix (default `0x06`) (`boot_logo.py:113`, `boot_logo.py:153`).
- Streamlit treats probe as advisory confidence, not strict model gate (`streamlit_ui.py:638`, `streamlit_ui.py:750`).

### 2.3 Framing/chunking

Frame format:
- `A5 | cmd | addr_hi | addr_lo | len_hi | len_lo | payload | crc_hi | crc_lo` (`logo_protocol.py:98`).

Chunking:
- Chunk size `1024` bytes (`logo_protocol.py:55`).
- Image payload `160*128*2 = 40960` bytes (`logo_protocol.py:52`).
- Full payload => 40 frames (validated by tests) (`tests/test_logo_protocol.py:21`).

Addressing mode:
- `byte`: addr = byte offset.
- `chunk`: addr = offset / chunk_size (`logo_protocol.py:154`).
- A5 configs default to `chunk` (`boot_logo.py:49`).

### 2.4 Checksums/CRC

- CRC algorithm: CRC16-XMODEM poly `0x1021`, init `0x0000` (`logo_protocol.py:68`).
- CRC scope: all bytes after start byte `0xA5` (`logo_protocol.py:73`, `logo_protocol.py:120`).
- CRC encoding: big-endian (`logo_protocol.py:74`, `logo_protocol.py:123`).

### 2.5 Command/response patterns

| Stage | Tx | Expected Rx | Validation logic |
|---|---|---|---|
| Handshake | `PROGRAMBFNORMALU` | `06` | exact byte compare (`logo_protocol.py:440`) |
| Enter mode | `44` | none | delay only (`logo_protocol.py:456`) |
| Init | frame cmd `0x02` payload `PROGRAM` | 9-byte A5 ACK frame | cmd must match; payload empty or starts `Y` (`logo_protocol.py:478`) |
| Config | frame cmd `0x04` addr `0x4504` payload `00000C000001` | 9-byte A5 ACK | same ACK rule (`logo_protocol.py:500`) |
| Setup | frame cmd `0x03` payload `00000C00` | 9-byte A5 ACK | same ACK rule (`logo_protocol.py:522`) |
| Write chunk | frame cmd `0x57` len `0x0400` (or short final chunk) | A5 `0xEE` OR A5 `0x57` with payload `Y` | dual ACK acceptance (`logo_protocol.py:579`) |
| Completion | frame cmd `0x06` payload `Over` | `00` or empty tolerated | non-zero warns, does not fail (`logo_protocol.py:615`) |

### 2.6 Retries/timeouts/backoff

Main app A5:
- Serial timeout default `2.0s` (`logo_protocol.py:359`).
- Pre-write retry attempts `2` (`logo_protocol.py:60`).
- Backoff `0.2s` (`logo_protocol.py:61`).
- No retries once chunk write begins (`logo_protocol.py:695`).

### 2.7 Write/verify/commit behavior

- No read-back verify in A5 uploader path.
- "Commit" equivalent is completion frame `CMD_COMPLETE` payload `Over` (`logo_protocol.py:603`).
- Returns success message after completion (`logo_protocol.py:699`).

### 2.8 Error handling and abort paths

Protocol aborts via `LogoProtocolError` on:
- Handshake mismatch (`logo_protocol.py:441`).
- Incomplete/invalid A5 responses (`logo_protocol.py:475`, `logo_protocol.py:497`, `logo_protocol.py:519`, `logo_protocol.py:572`).
- Unexpected ACK cmd/payload (`logo_protocol.py:479`, `logo_protocol.py:501`, `logo_protocol.py:523`, `logo_protocol.py:587`).
- Always closes serial in `finally` (`logo_protocol.py:701`).

## 3) Data Formats and Constants

### 3.1 Core A5 constants

| Constant | Value | Source |
|---|---:|---|
| Baud | `115200` | `logo_protocol.py:35` |
| Handshake magic | `PROGRAMBFNORMALU` | `logo_protocol.py:36` |
| Handshake ACK | `0x06` | `logo_protocol.py:37` |
| Logo mode cmd | `0x44` (`D`) | `logo_protocol.py:38` |
| CMD_INIT | `0x02` | `logo_protocol.py:41` |
| CMD_SETUP | `0x03` | `logo_protocol.py:42` |
| CMD_CONFIG | `0x04` | `logo_protocol.py:43` |
| CMD_COMPLETE | `0x06` | `logo_protocol.py:44` |
| CMD_WRITE | `0x57` | `logo_protocol.py:45` |
| CMD_DATA_ACK | `0xEE` | `logo_protocol.py:46` |
| Config addr | `0x4504` | `logo_protocol.py:49` |
| Chunk size | `1024` | `logo_protocol.py:55` |
| Config payload | `00 00 0C 00 00 01` | `logo_protocol.py:56` |
| Setup payload | `00 00 0C 00` | `logo_protocol.py:57` |

### 3.2 Payload/image encoding

| Field | Value | Source |
|---|---|---|
| Dimensions | `160x128` | `logo_protocol.py:52` |
| Pixel format | RGB565 little-endian word bytes | `logo_protocol.py:204`, `logo_protocol.py:251` |
| Pixel order options | `rgb` (default) or `bgr` | `logo_protocol.py:215` |
| Resize filter | PIL LANCZOS | `logo_protocol.py:232` |
| Row order | top-to-bottom, no vertical flip | `logo_protocol.py:237` |
| Total bytes | `40960` | `logo_protocol.py:54` |

### 3.3 Limits, offsets, alignment

- Expected exact payload size check in upload path (`logo_protocol.py:649`).
- Final chunk can be short if misaligned; warning emitted (`logo_protocol.py:550`).
- Configured operational mode for supported models is chunk-addressed, 1024-byte chunks (`boot_logo.py:49`).

## 4) Safety Gates and Destructive-Operation Protections

### 4.1 Core safety gate (authoritative)

`require_write_permission` rules (`core/safety.py:88`):
1. Simulation always allowed (`core/safety.py:117`).
2. `write_enabled` required (`core/safety.py:122`).
3. Unknown model denied (`core/safety.py:131`).
4. Unknown target region denied when no explicit target (`core/safety.py:141`).
5. Non-interactive token must match `WRITE` (`core/safety.py:149`).
6. Interactive prompt confirmation otherwise (`core/safety.py:159`).

Confirmation token:
- `CONFIRMATION_TOKEN = "WRITE"` (`core/safety.py:12`).

### 4.2 CLI protections

- `upload-logo-serial` requires explicit `--write`/confirmation when not dry-run (`cli.py:606`).
- Supports non-interactive scripted safety with `--confirm WRITE` (`cli.py:556`, `cli.py:165`).
- Uses shared core safety context and core flash action (`cli.py:617`, `cli.py:631`).

### 4.3 Streamlit protections (main app)

- Builds `SafetyContext` via `create_streamlit_safety_context` (`streamlit_ui.py:1195`).
- Actual write path still flows through `core.actions.flash_logo_serial` (`streamlit_ui.py:1218`).
- Identity probing is read-only and advisory (`streamlit_ui.py:638`, `streamlit_ui.py:750`).

## 5) Dependencies and Shared Utilities v2 Must Replicate

Protocol-critical logic:
- `crc16_xmodem`, `build_frame`, `parse_response`, `chunk_image_data`, `_calc_write_addr` (`logo_protocol.py:68`, `logo_protocol.py:94`, `logo_protocol.py:182`, `logo_protocol.py:129`, `logo_protocol.py:154`).
- Image conversion to RGB565 little-endian with selectable channel order (`logo_protocol.py:212`).

Transport semantics:
- 8N1 serial, DTR/RTS high, timeout handling, stale-buffer drain (`logo_protocol.py:379`, `logo_protocol.py:388`, `logo_protocol.py:398`).

Shared policy behavior:
- Safety gate contract (`core/safety.py:88`).
- A5-only config validation (`boot_logo.py:199`).

Python runtime deps that informed behavior:
- `pyserial`, `pillow` (`pyproject.toml:14`).

## 6) Gaps/Differences: Current `v2/web` vs Main

`v2/web` code present only as bundled artifact: `v2/web/dist/assets/index-C2p29bwN.js`.

| Topic | Main behavior | Current v2/web behavior | Impact |
|---|---|---|---|
| Source layout | Maintained Python source modules | No checked-in `v2/web/src`; only built JS bundle | Harder to audit/maintain parity over time. |
| Pre-write retry count | 2 attempts (`logo_protocol.py:60`) | 3 attempts (`index-C2p29bwN.js:41`, `ro=3`) | Different tolerance and timing profile. |
| Completion response tolerance | Empty or `0x00` accepted (`logo_protocol.py:615`) | Reads exactly 1 byte; timeout throws before tolerance check (`index-C2p29bwN.js:41`) | v2 can fail on radios that send no completion byte. |
| Safety gate | Centralized policy engine (`core/safety.py:88`) | UI checkbox + `window.prompt("WRITE")` (`index-C2p29bwN.js:41`) | Missing model/region-known policy checks and shared enforcement contract. |
| Identity confidence probe | Auto-probe + advisory read-only identity (`streamlit_ui.py:629`) | No handshake pre-probe before flash; only port selection (`index-C2p29bwN.js:41`) | Lower connection confidence UX, no high/medium confidence ranking. |
| Debug artifacts | payload, payload stream, frame stream, preview PNG, manifest (`logo_protocol.py:316`) | Downloads only `image_payload.bin` and `write_frames.bin` (`index-C2p29bwN.js:41`) | Reduced forensic parity with main debug outputs. |
| Config source | Registry-derived configs (`boot_logo.py:28`) | Hardcoded model array (`index-C2p29bwN.js:41`, `Tr=[...]`) | Risk of divergence when main registry changes. |
| Image conversion backend | PIL resize (LANCZOS) (`logo_protocol.py:232`) | Canvas `drawImage` + smoothing (`index-C2p29bwN.js:41`) | Potential pixel-level differences in payload bytes. |
| Address mode override | CLI supports `auto|byte|chunk` (`cli.py:571`) | Web appears fixed by selected profile default (`index-C2p29bwN.js:41`) | Less operator control for protocol experiments/recovery. |

## 7) Minimum Required Parity Checklist (v2/web)

- [ ] Use exact A5 frame layout and CRC16-XMODEM rules from `logo_protocol.py`.
- [ ] Keep command sequence ordering identical (handshake → D → init → config → setup → chunks → completion).
- [ ] Accept chunk ACK variants: `0xEE` OR `0x57`+`Y`.
- [ ] Match main completion tolerance: allow empty completion response without hard failure.
- [ ] Match model defaults: `chunk` addressing, 1024-byte chunks, RGB565 little-endian.
- [ ] Keep retry boundary: pre-write only; never retry after chunk data begins.
- [ ] Enforce shared safety semantics (write enable + confirmation token + model/region checks equivalent to `core/safety.py`).
- [ ] Keep identity probe non-destructive and advisory; do not hard-block valid A5-family variants by returned ID string.
- [ ] Emit equivalent debug artifacts (or documented equivalent) for deterministic byte-level comparison.
- [ ] Keep config values synchronized with registry-derived main values.

## 8) Test Coverage Map

### 8.1 Existing main tests validating protocol behavior

| Test file | Coverage |
|---|---|
| `tests/test_logo_protocol.py:15` | Config/setup payload constants match capture reference. |
| `tests/test_logo_protocol.py:21` | 40960-byte payload splits into 40 chunks of 1024. |
| `tests/test_logo_protocol.py:32` | First write frame has `A5`, `CMD_WRITE=0x57`, len `0x0400`. |
| `tests/test_logo_protocol.py:48` | RGB565 little-endian golden-vector bytes. |
| `tests/test_logo_protocol.py:72` | BGR565 override behavior. |
| `tests/test_boot_logo_flasher.py:27` | Supported A5 model set locked to `UV-5RM`, `UV-17Pro`, `UV-17R`. |
| `tests/test_boot_logo_flasher.py:32` | Enforces `a5_logo`, `write_addr_mode=chunk`, `chunk_size=1024`, `pixel_order=rgb`. |
| `tests/test_boot_logo_flasher.py:60` | Reject non-A5 protocol config. |
| `tests/test_boot_logo_flasher.py:84` | `read_radio_id` rejects non-uv17pro mode. |

Notably missing in main tests:
- End-to-end ACK-path tests for `LogoUploader` (including both chunk ACK variants).
- Explicit completion-empty-response acceptance test.
- Retry-boundary test proving no retry after first chunk write.

### 8.2 Recommended equivalent tests for `v2/web`

1. CRC parity test vector: TS `crc16Xmodem` equals Python output for known byte sequence.
2. Frame builder parity: exact bytes for init/config/setup/completion frames.
3. Chunk framing parity: 40960-byte payload => 40 write frames, chunk-address mode sequence `0..39`.
4. ACK acceptance tests: accept `0xEE` and `0x57+'Y'`; reject others.
5. Completion tolerance test: empty completion response should not fail.
6. Pre-write retry-only test: retries happen before first chunk; no retries after any chunk sent.
7. Safety policy tests: WRITE token checks, write-disabled rejection, unknown-model/unknown-region behavior.
8. Registry/config parity test: web profile constants match main `SERIAL_FLASH_CONFIGS` values.
9. Pixel conversion parity test: fixed image input hashes match Python payload hash.

## 9) Copyable TypeScript Interfaces (Inferred Mappings)

Inferred from Python structures and behavior (`core/safety.py`, `core/results.py`, `logo_protocol.py`, `boot_logo.py`).

```ts
// Inferred from core/safety.py:29
export interface SafetyContextLike {
  writeEnabled: boolean;
  confirmationToken?: string | null;
  interactive: boolean;
  modelDetected: string;
  regionKnown: boolean;
  simulate: boolean;
  warnings: string[];
}

// Inferred from core/results.py:12
export interface OperationResultLike {
  ok: boolean;
  operation: string;
  model?: string;
  region?: string;
  bytesLen?: number;
  hashes?: Record<string, string>;
  warnings?: string[];
  errors?: string[];
  metadata?: Record<string, unknown>;
  logs?: string[];
}

// Inferred from protocol/logo_protocol.py constants + builder
export type AddressMode = "byte" | "chunk";
export type PixelOrder = "rgb" | "bgr";

export interface A5Frame {
  start: 0xa5;
  cmd: number;      // 0x02,0x03,0x04,0x06,0x57,0xEE
  addr: number;     // uint16
  length: number;   // uint16
  payload: Uint8Array;
  crc16: number;    // uint16 big-endian on wire
}

export interface SerialFlashConfigLike {
  size: [number, number];
  colorMode: string;
  startAddr: number;
  baudrate: number;
  timeout: number;
  protocol: "a5_logo";
  writeAddrMode: AddressMode;
  chunkSize: 1024;
  pixelOrder: PixelOrder;
  magic: Uint8Array;        // PROGRAMBFNORMALU
  handshakeAck: Uint8Array; // 0x06
}

export interface UploadOptions {
  addressMode: AddressMode;
  pixelOrder: PixelOrder;
  handshakeProfile?: "normal" | "conservative";
  progress?: (written: number, total: number) => void;
  log?: (line: string) => void;
}
```

## 10) Explicit Assumptions and Unknowns

- `v2/web` source is not present (`v2/web/src` missing); comparison is against bundled file `v2/web/dist/assets/index-C2p29bwN.js` only.
- `LOGO_PROTOCOL.md` pixel-packing note says BGR565 (`LOGO_PROTOCOL.md:55`), but runtime defaults in code are RGB565 (`logo_protocol.py:243`, `boot_logo.py:51`). Treat runtime code as authoritative.
- A5 uploader currently does not verify response CRC in Python or web bundle; compatibility is based on header/cmd/payload checks.
- No main automated tests currently prove empty completion-byte tolerance or full transport-level retry semantics end-to-end.

## Implementation Order

1. Extract `v2/web` protocol code into source modules (transport, frame, crc, uploader, safety policy) to make behavior auditable.
2. Align constants/opcodes/payloads/addressing with `logo_protocol.py` and `boot_logo.py` defaults.
3. Adjust completion handling to match main tolerance (allow empty completion response).
4. Implement safety policy equivalent to `require_write_permission` (not just UI prompt).
5. Add advisory read-only identity probe and optional auto-selection ranking logic.
6. Add debug artifact parity (`payload`, `frame stream`, manifest/preview equivalent).
7. Add parity tests listed above, including byte-for-byte vectors against Python fixtures.
8. Wire profile config generation from a single shared config source (or generated artifact) to avoid hardcoded drift.
9. Run protocol dry-run comparisons (hashes/frame dumps) between Python main and web builds for identical inputs.
10. Only then enable/advertise protocol-compatibility in v2 release notes.
