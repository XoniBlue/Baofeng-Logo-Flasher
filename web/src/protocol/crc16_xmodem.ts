/** Computes CRC16-XMODEM checksum used by radio protocol frames. */
export function crc16Xmodem(data: Uint8Array): number {
  let crc = 0;
  for (const value of data) {
    crc ^= value << 8;
    for (let i = 0; i < 8; i += 1) {
      if (crc & 0x8000) {
        crc = (crc << 1) ^ 0x1021;
      } else {
        crc <<= 1;
      }
      crc &= 0xffff;
    }
  }
  return crc;
}
