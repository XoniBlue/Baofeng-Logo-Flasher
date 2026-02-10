/* eslint-disable @typescript-eslint/no-explicit-any */
declare global {
  interface Navigator {
    serial?: {
      requestPort(options?: any): Promise<any>;
      getPorts(): Promise<any[]>;
    };
  }
}

/** Minimal serial port contract used by the uploader and tests. */
export interface ReadWritePort {
  open(options: { baudRate: number; dataBits: 8; stopBits: 1; parity: "none"; flowControl: "none" }): Promise<void>;
  close(): Promise<void>;
  setSignals(signals: { dataTerminalReady?: boolean; requestToSend?: boolean }): Promise<void>;
  readable: ReadableStream<Uint8Array> | null;
  writable: WritableStream<Uint8Array> | null;
}

/** Thin wrapper around Web Serial with buffered reads and timeout-aware helpers. */
export class WebSerialPort {
  private port: ReadWritePort | null = null;
  private reader: ReadableStreamDefaultReader<Uint8Array> | null = null;
  private writer: WritableStreamDefaultWriter<Uint8Array> | null = null;
  private rxBuffer = new Uint8Array();
  private pendingRead: Promise<ReadableStreamReadResult<Uint8Array>> | null = null;

  /** Identifies locally-generated timeout errors so callers can retry slices safely. */
  private isReadTimeout(error: unknown): boolean {
    return error instanceof Error && error.message === "Read timeout";
  }

  /** Prompts user to select a serial device and stores it for later open(). */
  async requestPort(): Promise<void> {
    if (!navigator.serial) {
      throw new Error("Web Serial API is not available in this browser");
    }
    this.port = (await navigator.serial.requestPort()) as ReadWritePort;
  }

  /** Opens serial stream, sets modem lines high, and resets internal read state. */
  async open(baudRate: number): Promise<void> {
    if (!this.port) {
      throw new Error("No serial port selected");
    }
    await this.port.open({ baudRate, dataBits: 8, stopBits: 1, parity: "none", flowControl: "none" });
    await this.port.setSignals({ dataTerminalReady: true, requestToSend: true });

    if (!this.port.readable || !this.port.writable) {
      throw new Error("Serial stream is unavailable after open");
    }
    this.reader = this.port.readable.getReader();
    this.writer = this.port.writable.getWriter();
    this.rxBuffer = new Uint8Array();
    this.pendingRead = null;
  }

  /** Pulses DTR/RTS low then high to recover some radios before handshake. */
  async pulseSignals(lowMs = 40, highMs = 80): Promise<void> {
    if (!this.port) {
      throw new Error("Serial port not initialized");
    }
    await this.port.setSignals({ dataTerminalReady: false, requestToSend: false });
    await this.delay(lowMs);
    await this.port.setSignals({ dataTerminalReady: true, requestToSend: true });
    await this.delay(highMs);
  }

  /** Writes one raw buffer to serial stream. */
  async write(data: Uint8Array): Promise<void> {
    if (!this.writer) {
      throw new Error("Serial writer not initialized");
    }
    await this.writer.write(data);
  }

  /** Reads available bytes up to timeout, reusing a pending read across retries. */
  async readAtMost(timeoutMs: number): Promise<Uint8Array> {
    if (!this.reader) {
      throw new Error("Serial reader not initialized");
    }

    if (this.rxBuffer.length > 0) {
      // Serve unread/previously buffered bytes before touching the stream again.
      const data = this.rxBuffer;
      this.rxBuffer = new Uint8Array();
      return data;
    }

    if (!this.pendingRead) {
      // Reuse one outstanding reader.read() across timeout slices/callers.
      this.pendingRead = this.reader.read().finally(() => {
        this.pendingRead = null;
      });
    }

    let timeoutId = 0;
    const timeout = new Promise<never>((_, reject) => {
      timeoutId = window.setTimeout(() => reject(new Error("Read timeout")), timeoutMs);
    });

    const result = await Promise.race([this.pendingRead, timeout]);
    window.clearTimeout(timeoutId);
    if (result.done) {
      return new Uint8Array();
    }
    return result.value ?? new Uint8Array();
  }

  /** Pushes bytes back to front of internal buffer for subsequent reads. */
  unread(data: Uint8Array): void {
    if (data.length === 0) {
      return;
    }
    const merged = new Uint8Array(data.length + this.rxBuffer.length);
    merged.set(data, 0);
    merged.set(this.rxBuffer, data.length);
    this.rxBuffer = merged;
  }

  /** Reads exact byte count or throws timeout while preserving extra bytes in buffer. */
  async readExact(length: number, timeoutMs: number): Promise<Uint8Array> {
    if (length <= 0) {
      return new Uint8Array();
    }

    const deadline = Date.now() + timeoutMs;
    while (this.rxBuffer.length < length) {
      const remainingMs = deadline - Date.now();
      if (remainingMs <= 0) {
        throw new Error("Read timeout");
      }

      let chunk: Awaited<ReturnType<WebSerialPort["readAtMost"]>> = new Uint8Array(0);
      try {
        // Keep each wait short so deadline enforcement stays responsive.
        chunk = await this.readAtMost(Math.min(remainingMs, 120));
      } catch (error) {
        if (!this.isReadTimeout(error)) {
          throw error;
        }
        continue;
      }
      if (chunk.length === 0) {
        continue;
      }

      const merged = new Uint8Array(this.rxBuffer.length + chunk.length);
      merged.set(this.rxBuffer, 0);
      merged.set(chunk, this.rxBuffer.length);
      this.rxBuffer = merged;
    }

    // Return exactly requested bytes and preserve any extra for next read.
    const out = this.rxBuffer.slice(0, length);
    this.rxBuffer = this.rxBuffer.slice(length);
    return out;
  }

  /** Releases reader/writer and closes selected port. */
  async close(): Promise<void> {
    try {
      await this.reader?.cancel();
    } catch {
      // ignore
    }
    try {
      this.reader?.releaseLock();
    } catch {
      // ignore
    }
    try {
      this.writer?.releaseLock();
    } catch {
      // ignore
    }
    this.reader = null;
    this.writer = null;
    this.rxBuffer = new Uint8Array();
    this.pendingRead = null;
    if (this.port) {
      await this.port.close();
    }
  }

  /** Internal sleep helper used for signal pulse timing. */
  private async delay(ms: number): Promise<void> {
    await new Promise<void>((resolve) => {
      window.setTimeout(resolve, ms);
    });
  }
}
