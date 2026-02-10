/** Serial baud rate used by the target radios during logo transfer. */
export const BAUD_RATE = 115200;
/** Magic preamble sent before protocol frames to trigger bootloader handshake. */
export const HANDSHAKE_MAGIC = new Uint8Array([0x50, 0x52, 0x4f, 0x47, 0x52, 0x41, 0x4d, 0x42, 0x46, 0x4e, 0x4f, 0x52, 0x4d, 0x41, 0x4c, 0x55]);
/** ACK byte expected from the radio after handshake magic. */
export const HANDSHAKE_ACK = 0x06;
/** One-byte command that switches the radio into logo flashing mode. */
export const LOGO_MODE_CMD = 0x44;

/** Frame command for protocol initialization ("PROGRAM"). */
export const CMD_INIT = 0x02;
/** Frame command for setup parameters. */
export const CMD_SETUP = 0x03;
/** Frame command for flash configuration block. */
export const CMD_CONFIG = 0x04;
/** Frame command that finalizes transfer. */
export const CMD_COMPLETE = 0x06;
/** Frame command that writes one chunk of image data. */
export const CMD_WRITE = 0x57;
/** Device ACK command observed during chunk writes. */
export const CMD_DATA_ACK = 0xee;

/** Config frame address captured from the reference desktop app protocol. */
export const ADDR_CONFIG = 0x4504;

/** Required logo bitmap width in pixels. */
export const IMAGE_WIDTH = 160;
/** Required logo bitmap height in pixels. */
export const IMAGE_HEIGHT = 128;
/** Total payload size in bytes for RGB565 (2 bytes/pixel). */
export const IMAGE_BYTES = IMAGE_WIDTH * IMAGE_HEIGHT * 2;
/** Frame payload chunk size used by both web app and reference app. */
export const CHUNK_SIZE = 1024;

/** Static config payload emitted before setup and data frames. */
export const CONFIG_PAYLOAD = new Uint8Array([0x00, 0x00, 0x0c, 0x00, 0x00, 0x01]);
/** Static setup payload emitted right before first data chunk. */
export const SETUP_PAYLOAD = new Uint8Array([0x00, 0x00, 0x0c, 0x00]);

/** Number of full prewrite attempts before surfacing error. */
export const PREWRITE_MAX_ATTEMPTS = 2;
/** Delay between prewrite attempts for transient serial timing issues. */
export const PREWRITE_RETRY_DELAY_MS = 200;
/** Default handshake timeout used by "normal" profile. */
export const HANDSHAKE_TIMEOUT_MS = 4000;
/** Extended handshake timeout used by "conservative" profile. */
export const HANDSHAKE_TIMEOUT_CONSERVATIVE_MS = 7000;
/** Timeout for framed ACKs during prewrite exchange. */
export const PREWRITE_FRAME_TIMEOUT_MS = 3500;

/** Inter-frame and settle delays tuned to match working radio behavior. */
export const TIMING_MS = {
  openSettle: 100,
  handshake: 100,
  enterLogoMode: 200,
  init: 100,
  config: 20,
  setup: 20,
  writeChunk: 10,
  completion: 20
} as const;
