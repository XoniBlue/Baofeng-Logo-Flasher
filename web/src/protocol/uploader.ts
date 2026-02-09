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
  PREWRITE_FRAME_TIMEOUT_MS,
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
  prewriteRetryDelayMs: number;
}

export class LogoUploader {
  constructor(private readonly serial: WebSerialPort, private readonly timeoutMs = 2000) {}

  private isReadTimeout(error: unknown): boolean {
    return error instanceof Error && error.message === "Read timeout";
  }

  private async send(data: Uint8Array): Promise<void> {
    await this.serial.write(data);
  }

  private async recvAckFrame(timeoutMs: number): Promise<Uint8Array> {
    const deadline = Date.now() + timeoutMs;
    let collected = new Uint8Array(0);

    while (Date.now() < deadline) {
      const startIndex = collected.indexOf(0xa5);
      if (startIndex > 0) {
        collected = collected.slice(startIndex);
      } else if (startIndex < 0 && collected.length > 0) {
        // Keep only a tiny tail so noise does not grow unbounded while waiting for 0xA5.
        collected = collected.slice(-2);
      }

      if (collected.length >= 6) {
        const payloadLength = (collected[4] << 8) | collected[5];
        const frameLength = 1 + 1 + 2 + 2 + payloadLength + 2;
        if (payloadLength <= 32 && collected.length >= frameLength) {
          const frame = collected.slice(0, frameLength);
          const trailing = collected.slice(frameLength);
          if (trailing.length > 0) {
            this.serial.unread(trailing);
          }
          return frame;
        }
        if (payloadLength > 32) {
          // Header is likely junk despite the 0xA5 marker; resync one byte later.
          collected = collected.slice(1);
          continue;
        }
      }

      const remainingMs = deadline - Date.now();
      if (remainingMs <= 0) {
        break;
      }
      try {
        const chunk = await this.serial.readAtMost(Math.min(remainingMs, 120));
        if (chunk.length === 0) {
          continue;
        }
        const merged = new Uint8Array(collected.length + chunk.length);
        merged.set(collected, 0);
        merged.set(chunk, collected.length);
        collected = merged;
      } catch (error) {
        if (!this.isReadTimeout(error)) {
          throw error;
        }
      }
    }

    throw new Error(`Read timeout${collected.length > 0 ? ` (rx=${bytesToHex(collected)})` : ""}`);
  }

  private getHandshakeTiming(profile: HandshakeDelayProfile): HandshakeTiming {
    if (profile === "conservative") {
      return {
        profile,
        handshakeTimeoutMs: HANDSHAKE_TIMEOUT_CONSERVATIVE_MS,
        drainWindowMs: 900,
        prewriteRetryDelayMs: 350
      };
    }
    return {
      profile,
      handshakeTimeoutMs: HANDSHAKE_TIMEOUT_MS,
      drainWindowMs: 400,
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
      } catch (error) {
        if (!this.isReadTimeout(error)) {
          throw error;
        }
        // Timeout means no pending bytes for this slice.
      }
    }
  }

  async open(baudRate: number, drainWindowMs: number): Promise<void> {
    await this.serial.open(baudRate);
    await sleep(TIMING_MS.openSettle);
    await this.drainJunk(drainWindowMs);
  }

  private async readUntilContains(targetByte: number, timeoutMs: number): Promise<Uint8Array> {
    const deadline = Date.now() + timeoutMs;
    let collected = new Uint8Array(0);

    while (Date.now() < deadline) {
      const remainingMs = deadline - Date.now();
      if (remainingMs <= 0) {
        break;
      }

      try {
        const chunk = await this.serial.readAtMost(Math.min(remainingMs, 120));
        if (chunk.length === 0) {
          continue;
        }
        const merged = new Uint8Array(collected.length + chunk.length);
        merged.set(collected, 0);
        merged.set(chunk, collected.length);
        collected = merged;
        const ackIndex = collected.indexOf(targetByte);
        if (ackIndex >= 0) {
          return collected;
        }
      } catch (error) {
        if (!this.isReadTimeout(error)) {
          throw error;
        }
        // Timeout slice, continue polling until deadline.
      }
    }

    throw new Error(`Read timeout${collected.length > 0 ? ` (rx=${bytesToHex(collected)})` : ""}`);
  }

  async handshake(attempt: number, handshakeTimeoutMs: number, log?: UploadOptions["log"]): Promise<void> {
    const phases: Array<{ label: string; pulse: boolean; budget: number }> = [
      { label: "direct", pulse: false, budget: 0.6 },
      { label: "pulse-retry", pulse: true, budget: 0.4 }
    ];
    const failures: string[] = [];

    for (const phase of phases) {
      const phaseTimeoutMs = Math.max(300, Math.floor(handshakeTimeoutMs * phase.budget));
      try {
        if (phase.pulse) {
          log?.(`attempt ${attempt}: handshake ${phase.label} toggling DTR/RTS`);
          await this.serial.pulseSignals(80, 180);
        }
        log?.(`attempt ${attempt}: sending magic (${phase.label})`);
        await this.send(HANDSHAKE_MAGIC);
        await sleep(TIMING_MS.handshake);
        log?.(`attempt ${attempt}: waiting ack for ${phaseTimeoutMs} ms (${phase.label})`);
        const response = await this.readUntilContains(HANDSHAKE_ACK, phaseTimeoutMs);
        if (!response.includes(HANDSHAKE_ACK)) {
          failures.push(`${phase.label}=unexpected:${bytesToHex(response) || "empty"}`);
          continue;
        }
        return;
      } catch (error) {
        failures.push(`${phase.label}=${String(error)}`);
      }
    }
    throw new Error(`Handshake failed: ${failures.join("; ")}`);
  }

  async enterLogoMode(): Promise<void> {
    await this.send(new Uint8Array([LOGO_MODE_CMD]));
    await sleep(TIMING_MS.enterLogoMode);
  }

  async sendInitFrame(): Promise<void> {
    const frame = buildFrame(CMD_INIT, 0x0000, new Uint8Array([0x50, 0x52, 0x4f, 0x47, 0x52, 0x41, 0x4d]));
    await this.send(frame);
    await sleep(TIMING_MS.init);
    let response: Uint8Array;
    try {
      response = await this.recvAckFrame(Math.max(this.timeoutMs, PREWRITE_FRAME_TIMEOUT_MS));
    } catch (error) {
      throw new Error(`Init frame: ${String(error)}`);
    }
    this.expectAckFrame(response, CMD_INIT, "Init frame");
  }

  async sendConfigFrame(): Promise<void> {
    const frame = buildFrame(CMD_CONFIG, ADDR_CONFIG, CONFIG_PAYLOAD);
    await this.send(frame);
    await sleep(TIMING_MS.config);
    let response: Uint8Array;
    try {
      response = await this.recvAckFrame(Math.max(this.timeoutMs, PREWRITE_FRAME_TIMEOUT_MS));
    } catch (error) {
      throw new Error(`Config frame: ${String(error)}`);
    }
    this.expectAckFrame(response, CMD_CONFIG, "Config frame");
  }

  async sendSetupFrame(): Promise<void> {
    const frame = buildFrame(CMD_SETUP, 0x0000, SETUP_PAYLOAD);
    await this.send(frame);
    await sleep(TIMING_MS.setup);
    let response: Uint8Array;
    try {
      response = await this.recvAckFrame(Math.max(this.timeoutMs, PREWRITE_FRAME_TIMEOUT_MS));
    } catch (error) {
      throw new Error(`Setup frame: ${String(error)}`);
    }
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

  async sendImageData(
    imageData: Uint8Array,
    addressMode: AddressMode,
    progress?: UploadOptions["progress"],
    log?: UploadOptions["log"]
  ): Promise<UploadDebugArtifacts> {
    const chunks = chunkImageData(imageData, CHUNK_SIZE, false);
    const frames: Uint8Array[] = [];
    let sent = 0;
    const writeAckTimeoutMs = Math.max(this.timeoutMs, 3500);

    for (const chunk of chunks) {
      const addr = calcWriteAddr(chunk.offset, CHUNK_SIZE, addressMode);
      const frame = buildFrame(CMD_WRITE, addr, chunk.data);
      frames.push(frame);
      if (chunk.offset === 0) {
        log?.(`Prewrite complete; starting chunk upload (${chunks.length} chunks)`);
      }
      await this.send(frame);
      await sleep(TIMING_MS.writeChunk);
      const chunkTimeoutMs = chunk.offset === 0 ? Math.max(writeAckTimeoutMs, 4500) : writeAckTimeoutMs;
      let response: Uint8Array;
      try {
        response = await this.recvAckFrame(chunkTimeoutMs);
      } catch (error) {
        throw new Error(
          `Image data at offset 0x${chunk.offset.toString(16).padStart(4, "0")} (addr=0x${addr.toString(16).padStart(4, "0")}): ${String(error)}`
        );
      }
      if (response.length < 7) {
        throw new Error(
          `Image data at offset 0x${chunk.offset.toString(16).padStart(4, "0")} (addr=0x${addr.toString(16).padStart(4, "0")}): incomplete ACK (${response.length} bytes)`
        );
      }
      const parsed = parseResponse(response);
      const ackOk = parsed.cmd === CMD_DATA_ACK || (parsed.cmd === CMD_WRITE && parsed.payload[0] === 0x59);
      if (!ackOk) {
        throw new Error(
          `Image data at offset 0x${chunk.offset.toString(16).padStart(4, "0")} (addr=0x${addr.toString(16).padStart(4, "0")}): unexpected response ${bytesToHex(response)}`
        );
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
    let response: Awaited<ReturnType<WebSerialPort["readAtMost"]>>;
    try {
      response = await this.serial.readAtMost(this.timeoutMs);
    } catch {
      // Main app tolerates empty completion response, including timeout.
      response = new Uint8Array(0);
    }
    if (response.length > 0 && response[0] !== 0x00) {
      log?.(`Completion returned non-zero byte ${bytesToHex(response.slice(0, 1))}, continuing`);
    }
  }

  private async runPrewritePhase(timing: HandshakeTiming, log?: UploadOptions["log"]): Promise<void> {
    for (let attempt = 1; attempt <= PREWRITE_MAX_ATTEMPTS; attempt += 1) {
      const attemptStartedAt = Date.now();
      try {
        await this.open(BAUD_RATE, timing.drainWindowMs);
        log?.(`attempt ${attempt}: prewrite sync complete, entering protocol frames`);
        await this.handshake(attempt, timing.handshakeTimeoutMs, log);
        await this.enterLogoMode();
        await this.sendInitFrame();
        await this.sendConfigFrame();
        await this.sendSetupFrame();
        return;
      } catch (error) {
        const elapsedMs = Date.now() - attemptStartedAt;
        await this.serial.close();
        if (attempt >= PREWRITE_MAX_ATTEMPTS) {
          throw error;
        }
        log?.(`Prewrite attempt ${attempt}/${PREWRITE_MAX_ATTEMPTS} failed after ${elapsedMs} ms: ${String(error)}`);
        await sleep(timing.prewriteRetryDelayMs);
      }
    }
  }

  async probeIdentity(profile: HandshakeDelayProfile, log?: UploadOptions["log"]): Promise<boolean> {
    const profiles: HandshakeDelayProfile[] = profile === "conservative" ? ["conservative"] : ["normal", "conservative"];
    for (const candidate of profiles) {
      const timing = this.getHandshakeTiming(candidate);
      try {
        await this.open(BAUD_RATE, timing.drainWindowMs);
        await this.handshake(1, timing.handshakeTimeoutMs, log);
        if (candidate !== profile) {
          log?.(`Identity probe recovered with ${candidate} timing profile`);
        }
        return true;
      } catch (error) {
        log?.(`Identity probe failed (${candidate}): ${String(error)}`);
      } finally {
        await this.serial.close();
      }
    }
    return false;
  }

  async upload(imageData: Uint8Array, options: UploadOptions): Promise<UploadDebugArtifacts> {
    const requestedProfile = options.handshakeProfile ?? "normal";
    const profiles: HandshakeDelayProfile[] = requestedProfile === "conservative" ? ["conservative"] : ["normal", "conservative"];
    let prewriteError: unknown = new Error("Prewrite phase did not complete");
    for (const candidate of profiles) {
      const timing = this.getHandshakeTiming(candidate);
      options.log?.(`Handshake delay profile: ${timing.profile}`);
      try {
        await this.runPrewritePhase(timing, options.log);
        if (candidate !== requestedProfile) {
          options.log?.(`Prewrite recovered with ${candidate} timing profile`);
        }
        prewriteError = null;
        break;
      } catch (error) {
        prewriteError = error;
        if (candidate === profiles[profiles.length - 1]) {
          throw error;
        }
        options.log?.(`Falling back to conservative handshake timing after ${candidate} failure`);
      }
    }
    if (prewriteError) {
      throw prewriteError;
    }

    try {
      const debug = await this.sendImageData(imageData, options.addressMode, options.progress, options.log);
      await this.sendCompletionFrame(options.log);
      return debug;
    } finally {
      await this.serial.close();
    }
  }
}
