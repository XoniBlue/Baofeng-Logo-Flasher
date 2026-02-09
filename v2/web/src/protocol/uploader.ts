import {
  ADDR_CONFIG,
  BAUD_RATE,
  CHUNK_SIZE,
  CMD_COMPLETE,
  CMD_CONFIG,
  CMD_DATA_ACK,
  CMD_INIT,
  CMD_SETUP,
  CMD_WRITE,
  CONFIG_PAYLOAD,
  HANDSHAKE_ACK,
  HANDSHAKE_MAGIC,
  HANDSHAKE_TIMEOUT_CONSERVATIVE_MS,
  HANDSHAKE_TIMEOUT_MS,
  LOGO_MODE_CMD,
  PREWRITE_MAX_ATTEMPTS,
  PREWRITE_RETRY_DELAY_MS,
  SETUP_PAYLOAD,
  TIMING_MS
} from "./constants";
import { calcWriteAddr, chunkImageData } from "./chunking";
import { buildFrame, bytesToHex, parseResponse } from "./frame";
import { sleep } from "./utils";
import type { AddressMode, HandshakeDelayProfile, UploadOptions } from "./types";
import { WebSerialPort } from "../serial/webSerialPort";

export interface UploadDebugArtifacts {
  payload: Uint8Array;
  frameStream: Uint8Array;
  frameCount: number;
}

interface HandshakeTiming {
  profile: HandshakeDelayProfile;
  handshakeTimeoutMs: number;
  drainWindowMs: number;
  pulseLowMs: number;
  pulseHighMs: number;
  prewriteRetryDelayMs: number;
}

export class LogoUploader {
  constructor(private readonly serial: WebSerialPort, private readonly timeoutMs = 2000) {}

  private async send(data: Uint8Array): Promise<void> {
    await this.serial.write(data);
  }

  private async recv(length: number): Promise<Uint8Array> {
    return this.serial.readExact(length, this.timeoutMs);
  }

  private getHandshakeTiming(profile: HandshakeDelayProfile): HandshakeTiming {
    if (profile === "conservative") {
      return {
        profile,
        handshakeTimeoutMs: HANDSHAKE_TIMEOUT_CONSERVATIVE_MS,
        drainWindowMs: 320,
        pulseLowMs: 80,
        pulseHighMs: 180,
        prewriteRetryDelayMs: 350
      };
    }
    return {
      profile,
      handshakeTimeoutMs: HANDSHAKE_TIMEOUT_MS,
      drainWindowMs: 150,
      pulseLowMs: 40,
      pulseHighMs: 80,
      prewriteRetryDelayMs: PREWRITE_RETRY_DELAY_MS
    };
  }

  private async drainJunk(windowMs: number): Promise<void> {
    const deadline = Date.now() + windowMs;
    while (Date.now() < deadline) {
      const remainingMs = deadline - Date.now();
      if (remainingMs <= 0) {
        break;
      }
      try {
        await this.serial.readAtMost(Math.min(25, remainingMs));
      } catch {
        // Timeout means no pending bytes for this slice.
      }
    }
  }

  async open(baudRate: number, drainWindowMs: number): Promise<void> {
    await this.serial.open(baudRate);
    await sleep(TIMING_MS.openSettle);
    await this.drainJunk(drainWindowMs);
  }

  async handshake(attempt: number, handshakeTimeoutMs: number, log?: UploadOptions["log"]): Promise<void> {
    log?.(`attempt ${attempt}: sending magic`);
    await this.send(HANDSHAKE_MAGIC);
    await sleep(TIMING_MS.handshake);
    log?.(`attempt ${attempt}: waiting ack for ${handshakeTimeoutMs} ms`);
    const response = await this.serial.readExact(1, handshakeTimeoutMs);
    if (response.length !== 1 || response[0] !== HANDSHAKE_ACK) {
      throw new Error(`Handshake failed: expected 06 got ${bytesToHex(response) || "empty"}`);
    }
  }

  async enterLogoMode(): Promise<void> {
    await this.send(new Uint8Array([LOGO_MODE_CMD]));
    await sleep(TIMING_MS.enterLogoMode);
  }

  async sendInitFrame(): Promise<void> {
    const frame = buildFrame(CMD_INIT, 0x0000, new Uint8Array([0x50, 0x52, 0x4f, 0x47, 0x52, 0x41, 0x4d]));
    await this.send(frame);
    await sleep(TIMING_MS.init);
    const response = await this.recv(9);
    this.expectAckFrame(response, CMD_INIT, "Init frame");
  }

  async sendConfigFrame(): Promise<void> {
    const frame = buildFrame(CMD_CONFIG, ADDR_CONFIG, CONFIG_PAYLOAD);
    await this.send(frame);
    await sleep(TIMING_MS.config);
    const response = await this.recv(9);
    this.expectAckFrame(response, CMD_CONFIG, "Config frame");
  }

  async sendSetupFrame(): Promise<void> {
    const frame = buildFrame(CMD_SETUP, 0x0000, SETUP_PAYLOAD);
    await this.send(frame);
    await sleep(TIMING_MS.setup);
    const response = await this.recv(9);
    this.expectAckFrame(response, CMD_SETUP, "Setup frame");
  }

  private expectAckFrame(response: Uint8Array, expectedCmd: number, label: string): void {
    if (response.length < 7) {
      throw new Error(`${label}: incomplete response (${response.length} bytes)`);
    }
    const parsed = parseResponse(response);
    const payloadOk = parsed.payload.length === 0 || parsed.payload[0] === 0x59;
    if (parsed.cmd !== expectedCmd || !payloadOk) {
      throw new Error(`${label}: unexpected response ${bytesToHex(response)}`);
    }
  }

  async sendImageData(imageData: Uint8Array, addressMode: AddressMode, progress?: UploadOptions["progress"]): Promise<UploadDebugArtifacts> {
    const chunks = chunkImageData(imageData, CHUNK_SIZE, false);
    const frames: Uint8Array[] = [];
    let sent = 0;

    for (const chunk of chunks) {
      const addr = calcWriteAddr(chunk.offset, CHUNK_SIZE, addressMode);
      const frame = buildFrame(CMD_WRITE, addr, chunk.data);
      frames.push(frame);
      await this.send(frame);
      await sleep(TIMING_MS.writeChunk);

      const response = await this.recv(9);
      if (response.length < 7) {
        throw new Error(`Image data at offset 0x${chunk.offset.toString(16).padStart(4, "0")}: incomplete ACK (${response.length} bytes)`);
      }
      const parsed = parseResponse(response);
      const ackOk = parsed.cmd === CMD_DATA_ACK || (parsed.cmd === CMD_WRITE && parsed.payload[0] === 0x59);
      if (!ackOk) {
        throw new Error(`Image data at offset 0x${chunk.offset.toString(16).padStart(4, "0")}: unexpected response ${bytesToHex(response)}`);
      }

      sent += chunk.data.length;
      progress?.(sent, imageData.length);
    }

    const totalLen = frames.reduce((n, frame) => n + frame.length, 0);
    const frameStream = new Uint8Array(totalLen);
    let offset = 0;
    for (const frame of frames) {
      frameStream.set(frame, offset);
      offset += frame.length;
    }

    return {
      payload: imageData,
      frameStream,
      frameCount: frames.length
    };
  }

  async sendCompletionFrame(log?: UploadOptions["log"]): Promise<void> {
    const frame = buildFrame(CMD_COMPLETE, 0x0000, new Uint8Array([0x4f, 0x76, 0x65, 0x72]));
    await this.send(frame);
    await sleep(TIMING_MS.completion);
    const response = await this.recv(1);
    if (response.length > 0 && response[0] !== 0x00) {
      log?.(`Completion returned non-zero byte ${bytesToHex(response)}, continuing`);
    }
  }

  async upload(imageData: Uint8Array, options: UploadOptions): Promise<UploadDebugArtifacts> {
    const timing = this.getHandshakeTiming(options.handshakeProfile ?? "normal");
    options.log?.(`Handshake delay profile: ${timing.profile}`);

    let prewriteReady = false;
    for (let attempt = 1; attempt <= PREWRITE_MAX_ATTEMPTS; attempt += 1) {
      const attemptStartedAt = Date.now();
      try {
        await this.open(BAUD_RATE, timing.drainWindowMs);
        options.log?.(`attempt ${attempt}: pulsing signals`);
        await this.serial.pulseSignals(timing.pulseLowMs, timing.pulseHighMs);
        await this.handshake(attempt, timing.handshakeTimeoutMs, options.log);
        await this.enterLogoMode();
        await this.sendInitFrame();
        await this.sendConfigFrame();
        await this.sendSetupFrame();
        prewriteReady = true;
        break;
      } catch (error) {
        const elapsedMs = Date.now() - attemptStartedAt;
        await this.serial.close();
        if (attempt >= PREWRITE_MAX_ATTEMPTS) {
          throw error;
        }
        options.log?.(`Prewrite attempt ${attempt}/${PREWRITE_MAX_ATTEMPTS} failed after ${elapsedMs} ms: ${String(error)}`);
        await sleep(timing.prewriteRetryDelayMs);
      }
    }

    if (!prewriteReady) {
      throw new Error("Prewrite phase did not complete");
    }

    try {
      const debug = await this.sendImageData(imageData, options.addressMode, options.progress);
      await this.sendCompletionFrame(options.log);
      return debug;
    } finally {
      await this.serial.close();
    }
  }
}
