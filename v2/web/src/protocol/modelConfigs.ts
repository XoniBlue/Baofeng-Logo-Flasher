import type { AddressMode, PixelOrder } from "./types";

export interface SerialFlashConfig {
  model: "UV-5RM" | "UV-17Pro" | "UV-17R";
  size: [number, number];
  baudRate: number;
  timeoutMs: number;
  writeAddrMode: AddressMode;
  pixelOrder: PixelOrder;
}

export const SERIAL_FLASH_CONFIGS: SerialFlashConfig[] = [
  {
    model: "UV-5RM",
    size: [160, 128],
    baudRate: 115200,
    timeoutMs: 2000,
    writeAddrMode: "chunk",
    pixelOrder: "rgb"
  },
  {
    model: "UV-17Pro",
    size: [160, 128],
    baudRate: 115200,
    timeoutMs: 2000,
    writeAddrMode: "chunk",
    pixelOrder: "rgb"
  },
  {
    model: "UV-17R",
    size: [160, 128],
    baudRate: 115200,
    timeoutMs: 2000,
    writeAddrMode: "chunk",
    pixelOrder: "rgb"
  }
];
