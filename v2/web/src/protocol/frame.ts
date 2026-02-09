import { crc16Xmodem } from "./crc16_xmodem";
import type { ParsedResponse } from "./types";

export function buildFrame(cmd: number, addr: number, payload: Uint8Array): Uint8Array {
  const frame = new Uint8Array(1 + 1 + 2 + 2 + payload.length + 2);
  frame[0] = 0xa5;
  frame[1] = cmd & 0xff;
  frame[2] = (addr >> 8) & 0xff;
  frame[3] = addr & 0xff;
  frame[4] = (payload.length >> 8) & 0xff;
  frame[5] = payload.length & 0xff;
  frame.set(payload, 6);

  const crc = crc16Xmodem(frame.slice(1, frame.length - 2));
  frame[frame.length - 2] = (crc >> 8) & 0xff;
  frame[frame.length - 1] = crc & 0xff;
  return frame;
}

export function parseResponse(data: Uint8Array): ParsedResponse {
  if (data.length < 6 || data[0] !== 0xa5) {
    throw new Error(`Invalid response frame: ${bytesToHex(data)}`);
  }

  const cmd = data[1];
  const addr = (data[2] << 8) | data[3];
  const length = (data[4] << 8) | data[5];
  const payload = length > 0 ? data.slice(6, 6 + length) : new Uint8Array();

  return { cmd, addr, length, payload };
}

export function bytesToHex(bytes: Uint8Array): string {
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}
