/** How write frame addresses are encoded for the radio protocol. */
export type AddressMode = "byte" | "chunk";
/** Pixel channel interpretation when converting source images to RGB565. */
export type PixelOrder = "rgb" | "bgr";
/** Handshake timing profile for slower or noisier serial links. */
export type HandshakeDelayProfile = "normal" | "conservative";

/** Parsed protocol response metadata from a raw frame. */
export interface ParsedResponse {
  cmd: number;
  addr: number;
  length: number;
  payload: Uint8Array;
}

/** Upload behavior controls and optional UI callbacks. */
export interface UploadOptions {
  addressMode: AddressMode;
  pixelOrder: PixelOrder;
  handshakeProfile?: HandshakeDelayProfile;
  progress?: (sent: number, total: number) => void;
  log?: (line: string) => void;
}
