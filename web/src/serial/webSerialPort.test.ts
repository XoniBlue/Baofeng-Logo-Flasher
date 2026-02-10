import { describe, expect, it } from "vitest";
import type { ReadWritePort } from "./webSerialPort";
import { WebSerialPort } from "./webSerialPort";

/** Builds a fake ReadWritePort that delegates read behavior to provided implementation. */
function createFakePort(readImpl: () => Promise<ReadableStreamReadResult<Uint8Array>>): ReadWritePort {
  const reader = {
    read: readImpl,
    cancel: async (): Promise<void> => undefined,
    releaseLock: (): void => undefined
  } as unknown as ReadableStreamDefaultReader<Uint8Array>;

  const writer = {
    write: async (): Promise<void> => undefined,
    releaseLock: (): void => undefined
  } as unknown as WritableStreamDefaultWriter<Uint8Array>;

  const readable = {
    getReader: (): ReadableStreamDefaultReader<Uint8Array> => reader
  } as unknown as ReadableStream<Uint8Array>;

  const writable = {
    getWriter: (): WritableStreamDefaultWriter<Uint8Array> => writer
  } as unknown as WritableStream<Uint8Array>;

  return {
    open: async (): Promise<void> => undefined,
    close: async (): Promise<void> => undefined,
    setSignals: async (): Promise<void> => undefined,
    readable,
    writable
  };
}

/** Ensures pending read promise is reused across slice timeouts to avoid double reads. */
describe("WebSerialPort read timeout behavior", () => {
  it("reuses pending reader promise across timeout retries", async () => {
    let resolveRead: (value: ReadableStreamReadResult<Uint8Array>) => void = () => undefined;
    let readCalls = 0;
    const readImpl = (): Promise<ReadableStreamReadResult<Uint8Array>> => {
      readCalls += 1;
      return new Promise<ReadableStreamReadResult<Uint8Array>>((resolve) => {
        resolveRead = resolve;
      });
    };

    const serial = new WebSerialPort();
    (serial as unknown as { port: ReadWritePort }).port = createFakePort(readImpl);
    await serial.open(115200);

    const firstRead = serial.readAtMost(5);
    await expect(firstRead).rejects.toThrow("Read timeout");
    expect(readCalls).toBe(1);

    resolveRead({ done: false, value: new Uint8Array([0x06]) });

    await expect(serial.readAtMost(100)).resolves.toEqual(new Uint8Array([0x06]));
    expect(readCalls).toBe(1);
  });
});
