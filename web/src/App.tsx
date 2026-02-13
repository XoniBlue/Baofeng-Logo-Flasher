import { useEffect, useMemo, useRef, useState } from "react";
import { browserConstraintMessage, isWebSerialSupported } from "./compat/browserSupport";
import { CHUNK_SIZE, CMD_WRITE, IMAGE_BYTES } from "./protocol/constants";
import { chunkImageData, calcWriteAddr } from "./protocol/chunking";
import { buildFrame } from "./protocol/frame";
import { imageFileTo565 } from "./protocol/image565";
import { SERIAL_FLASH_CONFIGS } from "./protocol/modelConfigs";
import { requireWritePermission } from "./protocol/safety";
import { LogoUploader } from "./protocol/uploader";
import { WebSerialPort } from "./serial/webSerialPort";
import { loadModel, loadWriteMode, saveModel, saveWriteMode } from "./storage/settings";
import { FlashPanel } from "./ui/components/FlashPanel";
import { ImagePanel } from "./ui/components/ImagePanel";
import { PortPanel } from "./ui/components/PortPanel";
import { StatusLog } from "./ui/components/StatusLog";
import { fetchGlobalFlashCount, recordSuccessfulFlashOnce } from "./ui/flashCounter";
import { reportClientError } from "./ui/clientLogReporter";
import walkieTalkieIcon from "../walkie-talkie.svg";

/** Builds contiguous frame stream used by simulation mode and debug parity checks. */
function toFrameStream(payload: Uint8Array, mode: "byte" | "chunk"): Uint8Array {
  const chunks = chunkImageData(payload, CHUNK_SIZE, false);
  const frames = chunks.map((chunk) => {
    const addr = calcWriteAddr(chunk.offset, CHUNK_SIZE, mode);
    return buildFrame(CMD_WRITE, addr, chunk.data);
  });
  const total = frames.reduce((n, frame) => n + frame.length, 0);
  const stream = new Uint8Array(total);
  let offset = 0;
  for (const frame of frames) {
    stream.set(frame, offset);
    offset += frame.length;
  }
  return stream;
}

/** Top-level flasher UI and orchestration logic for image prep and upload actions. */
export default function App(): JSX.Element {
  const webSerialSupported = isWebSerialSupported();
  const defaultModel = SERIAL_FLASH_CONFIGS[0];
  const loadedModel = loadModel(defaultModel.model);
  const selectedFromStorage = SERIAL_FLASH_CONFIGS.find((item) => item.model === loadedModel) ?? defaultModel;

  const [selectedModel, setSelectedModel] = useState(selectedFromStorage);
  const [writeMode, setWriteMode] = useState(loadWriteMode());
  const [connected, setConnected] = useState(false);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [payload, setPayload] = useState<Uint8Array | null>(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const [logs, setLogs] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [totalFlashes, setTotalFlashes] = useState<number | null>(null);

  const serialRef = useRef(new WebSerialPort());

  const canFlash = useMemo(() => payload !== null && (!writeMode || connected), [payload, writeMode, connected]);

  /** Appends timestamped log lines for protocol and UI events. */
  const appendLog = (line: string): string => {
    const stamped = `[${new Date().toISOString()}] ${line}`;
    setLogs((prev) => [...prev, stamped]);
    return stamped;
  };

  useEffect(() => {
    let mounted = true;
    void fetchGlobalFlashCount()
      .then((count) => {
        if (mounted) {
          setTotalFlashes(count);
        }
      })
      .catch((counterError) => {
        console.error("Flash counter fetch failed:", counterError);
      });

    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    const handleWindowError = (event: ErrorEvent): void => {
      reportClientError({
        eventType: "window_error",
        message: event.message || "Unhandled window error",
        errorName: event.error?.name,
        stack: event.error?.stack,
        model: selectedModel.model,
        writeMode,
        connected
      });
    };
    const handleUnhandledRejection = (event: PromiseRejectionEvent): void => {
      const reason = event.reason;
      if (reason instanceof Error) {
        reportClientError({
          eventType: "unhandled_rejection",
          message: reason.message,
          errorName: reason.name,
          stack: reason.stack,
          model: selectedModel.model,
          writeMode,
          connected
        });
        return;
      }
      reportClientError({
        eventType: "unhandled_rejection",
        message: String(reason ?? "Unhandled rejection"),
        model: selectedModel.model,
        writeMode,
        connected
      });
    };

    window.addEventListener("error", handleWindowError);
    window.addEventListener("unhandledrejection", handleUnhandledRejection);
    return () => {
      window.removeEventListener("error", handleWindowError);
      window.removeEventListener("unhandledrejection", handleUnhandledRejection);
    };
  }, [connected, selectedModel.model, writeMode]);

  /** Converts selected file into normalized RGB565 payload and preview image. */
  const onSelectFile = async (file: File): Promise<void> => {
    setError("");
    setSuccess("");
    const converted = await imageFileTo565(file, selectedModel.pixelOrder);
    if (converted.bytes.length !== IMAGE_BYTES) {
      throw new Error(`Payload size mismatch: expected ${IMAGE_BYTES}, got ${converted.bytes.length}`);
    }
    setPayload(converted.bytes);
    setPreviewUrl(converted.previewUrl);
    appendLog(`Image prepared (${converted.bytes.length} bytes)`);
  };

  /** Requests serial port and runs advisory probe without writing image data. */
  const onConnect = async (): Promise<void> => {
    setError("");
    setSuccess("");
    const connectLogs: string[] = [];
    const logConnect = (line: string): void => {
      connectLogs.push(appendLog(line));
    };
    try {
      await serialRef.current.requestPort();
      setConnected(true);
      logConnect("Serial port selected");
      const probeUploader = new LogoUploader(serialRef.current, selectedModel.timeoutMs);
      const probeOk = await probeUploader.probeIdentity(logConnect);
      if (probeOk) {
        setSuccess("Advisory probe succeeded. Radio responded to A5 handshake.");
        logConnect("Advisory identity probe: high confidence (A5 handshake ACK)");
      } else {
        logConnect("Advisory identity probe: low confidence (no A5 handshake ACK)");
      }
    } catch (connectError) {
      const errorText = String(connectError);
      setError(errorText);
      reportClientError({
        eventType: "connect_error",
        message: errorText,
        errorName: connectError instanceof Error ? connectError.name : undefined,
        stack: connectError instanceof Error ? connectError.stack : undefined,
        model: selectedModel.model,
        writeMode,
        connected,
        logLines: connectLogs
      });
    }
  };

  /** Runs simulation or full upload depending on write mode toggle. */
  const onFlash = async (): Promise<void> => {
    if (!payload) {
      setError("Select an image first.");
      return;
    }
    setBusy(true);
    setError("");
    setSuccess("");
    setProgress(0);

    const flashLogs: string[] = [];
    const logFlash = (line: string): void => {
      flashLogs.push(appendLog(line));
    };

    try {
      const addressMode = "chunk" as const;
      logFlash(`Write address mode: ${addressMode.toUpperCase()}`);

      if (!writeMode) {
        const frameStream = toFrameStream(payload, addressMode);
        setProgress(100);
        setSuccess("Simulation complete.");
        logFlash(`Simulation complete (${frameStream.length} frame-stream bytes)`);
        return;
      }

      // Explicit confirmation gate before any irreversible device write.
      const token = window.prompt("Type WRITE to confirm radio write:");
      requireWritePermission({
        writeEnabled: writeMode,
        confirmationToken: token,
        interactive: true,
        modelDetected: selectedModel.model,
        regionKnown: SERIAL_FLASH_CONFIGS.some((cfg) => cfg.model === selectedModel.model),
        simulate: false
      });

      const flashSessionId = crypto.randomUUID();
      const uploader = new LogoUploader(serialRef.current, selectedModel.timeoutMs);
      const { frameCount } = await uploader.upload(payload, {
        addressMode,
        pixelOrder: selectedModel.pixelOrder,
        progress: (sent, total) => {
          setProgress(Math.min(100, Math.floor((sent / total) * 100)));
        },
        log: logFlash
      });

      // Counter update is fire-and-forget so UI success is not blocked by network.
      void recordSuccessfulFlashOnce({
        sessionId: flashSessionId,
        model: selectedModel.model,
        writeMode,
        connected,
        logLines: flashLogs
      }).then((updatedCount) => {
        if (updatedCount !== null) {
          setTotalFlashes(updatedCount);
        }
      });

      setProgress(100);
      setSuccess("Flash complete. Power cycle the radio to view the logo.");
      logFlash(`Flash complete (${frameCount} frames)`);
    } catch (flashError) {
      const errorText = String(flashError);
      setError(errorText);
      flashLogs.push(appendLog(`Error: ${errorText}`));
      reportClientError({
        eventType: "flash_error",
        message: errorText,
        errorName: flashError instanceof Error ? flashError.name : undefined,
        stack: flashError instanceof Error ? flashError.stack : undefined,
        model: selectedModel.model,
        writeMode,
        connected,
        logLines: flashLogs
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="app-shell">
      <header className="hero">
        <h1><img className="title-icon" src={walkieTalkieIcon} alt="Handheld radio" /> Baofeng UV Logo Flasher</h1>
        <p>Chrome-only Web Serial flasher for UV-5RM and UV-17-family radios.</p>
        <div className="hero-badges">
          <div className="flash-counter-badge" role="status" aria-live="polite">
            <span className="flash-counter-badge-label">Total flashes</span>
            <span className="flash-counter-badge-value">{totalFlashes ?? "..."}</span>
          </div>
          <a className="info-badge" href="https://github.com/XoniBlue/Baofeng-Logo-Flasher" target="_blank" rel="noreferrer">
            <span className="info-badge-label">Repo</span>
            <span className="info-badge-value">Baofeng-Logo-Flasher</span>
          </a>
        </div>
      </header>

      {!webSerialSupported ? <div className="error">{browserConstraintMessage()}</div> : null}

      <section className="panel">
        <h2>Profile</h2>
        <label htmlFor="model">Model</label>
        <select
          id="model"
          value={selectedModel.model}
          onChange={(event) => {
            const selected = SERIAL_FLASH_CONFIGS.find((item) => item.model === event.currentTarget.value);
            if (selected) {
              setSelectedModel(selected);
              saveModel(selected.model);
            }
          }}
        >
          {SERIAL_FLASH_CONFIGS.map((item) => (
            <option key={item.model} value={item.model}>
              {item.model}
            </option>
          ))}
        </select>
      </section>

      <div className="grid">
        <PortPanel connected={connected} onConnect={onConnect} disabled={!webSerialSupported || busy} />
        <ImagePanel
          previewUrl={previewUrl}
          onSelectFile={async (file) => {
            try {
              await onSelectFile(file);
            } catch (imageError) {
              setError(String(imageError));
            }
          }}
        />
      </div>

      <FlashPanel
        writeMode={writeMode}
        progress={progress}
        busy={busy}
        canFlash={canFlash}
        onWriteModeChange={(enabled) => {
          setWriteMode(enabled);
          saveWriteMode(enabled);
        }}
        onFlash={onFlash}
      />

      {error ? <div className="error">{error}</div> : null}
      {success ? <div className="success">{success}</div> : null}

      <section className="panel">
        <h2>Logs</h2>
        <StatusLog logs={logs} />
      </section>
    </main>
  );
}
