export type AddressMode = "byte" | "chunk";
export type PixelOrder = "rgb" | "bgr";
export type HandshakeDelayProfile = "normal" | "conservative";

export interface ParsedResponse {
  cmd: number;
  addr: number;
  length: number;
  payload: Uint8Array;
}

export interface UploadOptions {
  addressMode: AddressMode;
  pixelOrder: PixelOrder;
  handshakeProfile?: HandshakeDelayProfile;
  progress?: (sent: number, total: number) => void;
  log?: (line: string) => void;
}
