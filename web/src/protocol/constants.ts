export const BAUD_RATE = 115200;
export const HANDSHAKE_MAGIC = new Uint8Array([0x50, 0x52, 0x4f, 0x47, 0x52, 0x41, 0x4d, 0x42, 0x46, 0x4e, 0x4f, 0x52, 0x4d, 0x41, 0x4c, 0x55]);
export const HANDSHAKE_ACK = 0x06;
export const LOGO_MODE_CMD = 0x44;

export const CMD_INIT = 0x02;
export const CMD_SETUP = 0x03;
export const CMD_CONFIG = 0x04;
export const CMD_COMPLETE = 0x06;
export const CMD_WRITE = 0x57;
export const CMD_DATA_ACK = 0xee;

export const ADDR_CONFIG = 0x4504;

export const IMAGE_WIDTH = 160;
export const IMAGE_HEIGHT = 128;
export const IMAGE_BYTES = IMAGE_WIDTH * IMAGE_HEIGHT * 2;
export const CHUNK_SIZE = 1024;

export const CONFIG_PAYLOAD = new Uint8Array([0x00, 0x00, 0x0c, 0x00, 0x00, 0x01]);
export const SETUP_PAYLOAD = new Uint8Array([0x00, 0x00, 0x0c, 0x00]);

export const PREWRITE_MAX_ATTEMPTS = 3;
export const PREWRITE_RETRY_DELAY_MS = 200;
export const HANDSHAKE_TIMEOUT_MS = 4000;
export const HANDSHAKE_TIMEOUT_CONSERVATIVE_MS = 7000;

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
