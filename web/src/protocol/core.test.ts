import { describe, expect, it } from "vitest";
import { CHUNK_SIZE } from "./constants";
import { chunkImageData, calcWriteAddr } from "./chunking";
import { crc16Xmodem } from "./crc16_xmodem";
import { buildFrame } from "./frame";
import { rgbaTo565Bytes } from "./image565";

/** Helper to keep expected byte assertions readable in tests. */
function hex(bytes: Uint8Array): string {
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

/** Core protocol parity tests for framing, CRC, chunking, and RGB conversion. */
describe("protocol core", () => {
  it("computes crc16 xmodem for PROGRAM", () => {
    const input = new TextEncoder().encode("PROGRAM");
    expect(crc16Xmodem(input)).toBe(0xcd59);
  });

  it("builds init frame with expected header", () => {
    const payload = new TextEncoder().encode("PROGRAM");
    const frame = buildFrame(0x02, 0x0000, payload);
    expect(frame[0]).toBe(0xa5);
    expect(frame[1]).toBe(0x02);
    expect(frame[4]).toBe(0x00);
    expect(frame[5]).toBe(0x07);
  });

  it("chunks full payload into 40 write chunks", () => {
    const payload = new Uint8Array(40960);
    const chunks = chunkImageData(payload, CHUNK_SIZE, false);
    expect(chunks).toHaveLength(40);
    expect(calcWriteAddr(chunks[0].offset, CHUNK_SIZE, "chunk")).toBe(0);
    expect(calcWriteAddr(chunks[39].offset, CHUNK_SIZE, "chunk")).toBe(39);
  });

  it("converts known RGB pixels to RGB565 little-endian bytes", () => {
    const rgba = new Uint8ClampedArray([
      255, 0, 0, 255,
      0, 255, 0, 255,
      0, 0, 255, 255,
      255, 255, 255, 255
    ]);
    expect(hex(rgbaTo565Bytes(rgba, "rgb"))).toBe("00f8e0071f00ffff");
  });
});
