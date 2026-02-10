import { describe, expect, it } from "vitest";
import { PREWRITE_MAX_ATTEMPTS } from "./constants";
import { LogoUploader } from "./uploader";
import type { WebSerialPort } from "../serial/webSerialPort";

/** Deterministic serial stub used to script read sequences for uploader tests. */
class FakeSerialPort {
  private readQueue: Array<Uint8Array | Error>;
  private unreadBuffer = new Uint8Array(0);

  constructor(readQueue: Array<Uint8Array | Error> = []) {
    this.readQueue = [...readQueue];
  }

  async open(): Promise<void> {}
  async write(): Promise<void> {}
  async close(): Promise<void> {}
  async pulseSignals(): Promise<void> {}
  async readExact(): Promise<Uint8Array> {
    return new Uint8Array([0x06]);
  }
  async readAtMost(): Promise<Uint8Array> {
    if (this.unreadBuffer.length > 0) {
      const out = this.unreadBuffer;
      this.unreadBuffer = new Uint8Array(0);
      return out;
    }
    if (this.readQueue.length === 0) {
      throw new Error("Read timeout");
    }
    const next = this.readQueue.shift() as Uint8Array | Error;
    if (next instanceof Error) {
      throw next;
    }
    return next;
  }
  unread(data: Uint8Array): void {
    if (data.length === 0) {
      return;
    }
    const merged = new Uint8Array(data.length + this.unreadBuffer.length);
    merged.set(data, 0);
    merged.set(this.unreadBuffer, data.length);
    this.unreadBuffer = merged;
  }
}

/** Regression tests for protocol parity and error-tolerant handshake/ACK parsing. */
describe("uploader parity", () => {
  it("matches main prewrite retry count", () => {
    expect(PREWRITE_MAX_ATTEMPTS).toBe(2);
  });

  it("tolerates missing completion response", async () => {
    const uploader = new LogoUploader(new FakeSerialPort() as unknown as WebSerialPort, 10);
    await expect(uploader.sendCompletionFrame()).resolves.toBeUndefined();
  });

  it("accepts handshake ack even with leading junk bytes", async () => {
    const serial = new FakeSerialPort([new Uint8Array([0x00, 0x12]), new Uint8Array([0x99, 0x06])]);
    const uploader = new LogoUploader(serial as unknown as WebSerialPort, 50);
    await expect(uploader.handshake(1, 200, () => undefined)).resolves.toBeUndefined();
  });

  it("succeeds on pulse-retry handshake phase", async () => {
    const serial = new FakeSerialPort([new Error("Read timeout"), new Uint8Array([0x06])]);
    const uploader = new LogoUploader(serial as unknown as WebSerialPort, 50);
    await expect(uploader.handshake(1, 400, () => undefined)).resolves.toBeUndefined();
  });

  it("ignores trailing handshake noise before init ACK frame", async () => {
    const initAck = new Uint8Array([0xa5, 0x02, 0x00, 0x00, 0x00, 0x00, 0x12, 0x34]);
    const serial = new FakeSerialPort([new Uint8Array([0x06, 0xff]), initAck]);
    const uploader = new LogoUploader(serial as unknown as WebSerialPort, 100);
    await expect(uploader.handshake(1, 200, () => undefined)).resolves.toBeUndefined();
    await expect(uploader.sendInitFrame()).resolves.toBeUndefined();
  });

  it("parses config ACK frame with leading junk and split chunks", async () => {
    const serial = new FakeSerialPort([
      new Uint8Array([0x99, 0x88]),
      new Uint8Array([0xa5, 0x04, 0x45]),
      new Uint8Array([0x04, 0x00, 0x00, 0xab, 0xcd])
    ]);
    const uploader = new LogoUploader(serial as unknown as WebSerialPort, 100);
    await expect(uploader.sendConfigFrame()).resolves.toBeUndefined();
  });
});
