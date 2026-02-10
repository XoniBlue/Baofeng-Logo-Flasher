import type { AddressMode } from "./types";

/** One protocol write unit with original image offset and payload bytes. */
export interface Chunk {
  offset: number;
  data: Uint8Array;
}

/** Splits image payload into protocol-sized blocks, optionally zero-padding tail. */
export function chunkImageData(imageData: Uint8Array, chunkSize: number, padLastChunk = false): Chunk[] {
  const chunks: Chunk[] = [];
  for (let offset = 0; offset < imageData.length; offset += chunkSize) {
    let chunk = imageData.slice(offset, offset + chunkSize);
    if (padLastChunk && chunk.length < chunkSize) {
      const padded = new Uint8Array(chunkSize);
      padded.set(chunk);
      chunk = padded;
    }
    chunks.push({ offset, data: chunk });
  }
  return chunks;
}

/** Converts byte offset to on-wire address according to selected write mode. */
export function calcWriteAddr(offset: number, chunkSize: number, mode: AddressMode): number {
  if (mode === "byte") {
    return offset;
  }
  if (mode === "chunk") {
    return Math.floor(offset / chunkSize);
  }
  throw new Error(`Unknown write address mode: ${String(mode)}`);
}
