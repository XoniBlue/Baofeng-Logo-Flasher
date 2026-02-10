import { IMAGE_HEIGHT, IMAGE_WIDTH } from "./constants";
import type { PixelOrder } from "./types";

/** Converts one RGB888 pixel to RGB565 value. */
export function rgb888ToRgb565(r: number, g: number, b: number): number {
  const r5 = (r >> 3) & 0x1f;
  const g6 = (g >> 2) & 0x3f;
  const b5 = (b >> 3) & 0x1f;
  return (r5 << 11) | (g6 << 5) | b5;
}

/** Converts one RGB888 pixel to BGR565 value for models that swap red/blue. */
function rgb888ToBgr565(r: number, g: number, b: number): number {
  const r5 = (r >> 3) & 0x1f;
  const g6 = (g >> 2) & 0x3f;
  const b5 = (b >> 3) & 0x1f;
  return (b5 << 11) | (g6 << 5) | r5;
}

/** Converts RGBA canvas pixels into little-endian 16-bit RGB565/BGR565 byte stream. */
export function rgbaTo565Bytes(rgba: Uint8ClampedArray, pixelOrder: PixelOrder): Uint8Array {
  const out = new Uint8Array((rgba.length / 4) * 2);
  let j = 0;
  for (let i = 0; i < rgba.length; i += 4) {
    const r = rgba[i];
    const g = rgba[i + 1];
    const b = rgba[i + 2];
    const value = pixelOrder === "rgb" ? rgb888ToRgb565(r, g, b) : rgb888ToBgr565(r, g, b);
    out[j] = value & 0xff;
    out[j + 1] = (value >> 8) & 0xff;
    j += 2;
  }
  return out;
}

/** Normalizes an arbitrary image file to 160x128 and returns converted payload plus preview image. */
export async function imageFileTo565(file: File, pixelOrder: PixelOrder): Promise<{ bytes: Uint8Array; previewUrl: string }> {
  const bitmap = await createImageBitmap(file);
  const canvas = document.createElement("canvas");
  canvas.width = IMAGE_WIDTH;
  canvas.height = IMAGE_HEIGHT;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) {
    throw new Error("Canvas 2D context unavailable");
  }

  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = "high";
  ctx.fillStyle = "#000000";
  ctx.fillRect(0, 0, IMAGE_WIDTH, IMAGE_HEIGHT);
  ctx.drawImage(bitmap, 0, 0, IMAGE_WIDTH, IMAGE_HEIGHT);

  const imageData = ctx.getImageData(0, 0, IMAGE_WIDTH, IMAGE_HEIGHT);
  const bytes = rgbaTo565Bytes(imageData.data, pixelOrder);
  const previewUrl = canvas.toDataURL("image/png");
  return { bytes, previewUrl };
}
