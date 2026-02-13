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
import { ConfirmWriteModal } from "./ui/components/ConfirmWriteModal";
import { fetchGlobalFlashCount, recordSuccessfulFlashOnce } from "./ui/flashCounter";
import { reportClientError } from "./ui/clientLogReporter";
import { friendlyErrorMessage } from "./ui/errorMessages";
import walkieTalkieIcon from "../walkie-talkie.svg";
import packageJson from "../package.json";

/** Log entry with severity level for visual differentiation. */
export interface LogEntry {
  timestamp: string;
  message: string;
  level: "info" | "success" | "error" | "warn";
}

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

/** Detects mobile devices that cannot support Web Serial. */
function isMobileDevice(): boolean {
  return /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
}

/** Top-level flasher UI and orchestration logic for image prep and upload actions. */
export default function App(): JSX.Element {
  const appSemver = packageJson.version;
  const webSerialSupported = isWebSerialSupported();
  const isMobile = isMobileDevice();
  const defaultModel = SERIAL_FLASH_CONFIGS[0];
  const loadedModel = loadModel(defaultModel.model);
  const selectedFromStorage = SERIAL_FLASH_CONFIGS.find((item) => item.model === loadedModel) ?? defaultModel;

  const [selectedModel, setSelectedModel] = useState(selectedFromStorage);
  const [writeMode, setWriteMode] = useState(loadWriteMode());
  const [connected, setConnected] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [operationStatus, setOperationStatus] = useState("");
  const [payload, setPayload] = useState<Uint8Array | null>(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const [selectedFileName, setSelectedFileName] = useState("");
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [totalFlashes, setTotalFlashes] = useState<number | null>(null);
  const [showWriteModal, setShowWriteModal] = useState(false);

  const serialRef = useRef(new WebSerialPort());

  const canFlash = useMemo(() => payload !== null && (!writeMode || connected), [payload, writeMode, connected]);

  /** Appends timestamped log lines for protocol and UI events with severity level. */
  const appendLog = (line: string, level: LogEntry["level"] = "info"): string => {
    const timestamp = new Date().toISOString();
    const entry: LogEntry = { timestamp, message: line, level };
    setLogs((prev) => [...prev, entry]);
    return `[${timestamp}] ${line}`;
  };

  // Cache and load flash counter from localStorage for instant display
  useEffect(() => {
    let mounted = true;
    
    // Load cached count immediately
    const cached = localStorage.getItem("lastKnownFlashCount");
    if (cached) {
      setTotalFlashes(parseInt(cached, 10));
    }

    // Fetch fresh count in background
    void fetchGlobalFlashCount()
      .then((count) => {
        if (mounted) {
          setTotalFlashes(count);
          localStorage.setItem("lastKnownFlashCount", String(count));
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
    setSelectedFileName(file.name);
    appendLog(`Image prepared: ${file.name} (${converted.bytes.length} bytes)`, "success");
  };

  /** Requests serial port and runs advisory probe without writing image data. */
  const onConnect = async (): Promise<void> => {
    setError("");
    setSuccess("");
    setConnecting(true);
    setOperationStatus("Connecting to serial port...");
    const connectLogs: string[] = [];
    const logConnect = (line: string): void => {
      connectLogs.push(appendLog(line));
    };
    try {
      await serialRef.current.requestPort();
      setConnected(true);
      logConnect("Serial port selected");
      
      setOperationStatus("Probing radio identity...");
      const probeUploader = new LogoUploader(serialRef.current, selectedModel.timeoutMs);
      const probeOk = await probeUploader.probeIdentity(logConnect);
      
      if (probeOk) {
        setSuccess("Connected! Radio responded to handshake.");
        appendLog("Advisory identity probe: high confidence (A5 handshake ACK)", "success");
      } else {
        appendLog("Advisory identity probe: low confidence (no A5 handshake ACK)", "warn");
      }
    } catch (connectError) {
      const errorText = friendlyErrorMessage(connectError);
      setError(errorText);
      appendLog(`Connection error: ${errorText}`, "error");
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
    } finally {
      setConnecting(false);
      setOperationStatus("");
    }
  };

  /** Disconnects from serial port. */
  const onDisconnect = async (): Promise<void> => {
    try {
      await serialRef.current.close();
      setConnected(false);
      setSuccess("");
      appendLog("Disconnected from serial port", "info");
    } catch (disconnectError) {
      const errorText = friendlyErrorMessage(disconnectError);
      setError(errorText);
      appendLog(`Disconnect error: ${errorText}`, "error");
    }
  };

  /** Initiates flash process, showing modal for write mode confirmation. */
  const onFlashClick = (): void => {
    if (!payload) {
      setError("Select an image first.");
      return;
    }

    if (writeMode) {
      setShowWriteModal(true);
    } else {
      void onFlash(false);
    }
  };

  /** Runs simulation or full upload depending on write mode toggle. */
  const onFlash = async (confirmed: boolean): Promise<void> => {
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
        setOperationStatus("Running simulation...");
        const frameStream = toFrameStream(payload, addressMode);
        setProgress(100);
        setSuccess("Simulation complete! Frame generation successful.");
        appendLog(`Simulation complete (${frameStream.length} frame-stream bytes)`, "success");
        setOperationStatus("");
        return;
      }

      // Write mode with explicit confirmation
      if (!confirmed) {
        setBusy(false);
        return;
      }

      requireWritePermission({
        writeEnabled: writeMode,
        confirmationToken: "WRITE",
        interactive: false,
        modelDetected: selectedModel.model,
        regionKnown: SERIAL_FLASH_CONFIGS.some((cfg) => cfg.model === selectedModel.model),
        simulate: false
      });

      setOperationStatus("Writing to radio...");
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
          localStorage.setItem("lastKnownFlashCount", String(updatedCount));
        }
      });

      setProgress(100);
      setSuccess("Flash complete!");
      appendLog(`Flash complete (${frameCount} frames)`, "success");
    } catch (flashError) {
      const errorText = friendlyErrorMessage(flashError);
      setError(errorText);
      appendLog(`Flash error: ${errorText}`, "error");
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
      setOperationStatus("");
    }
  };

  // Mobile device blocker
  if (isMobile) {
    return (
      <div className="device-blocker">
        <div className="device-blocker-content">
          <h1>📱 Mobile Not Supported</h1>
          <p>This tool requires <strong>Web Serial API</strong>, which is not available on mobile browsers.</p>
          <p><strong>Please use a desktop browser:</strong></p>
          <ul>
            <li>Chrome (recommended)</li>
            <li>Edge</li>
            <li>Brave</li>
            <li>Opera</li>
          </ul>
          <p className="muted">Web Serial requires direct USB access, which is unavailable on mobile operating systems.</p>
        </div>
      </div>
    );
  }

  // Browser compatibility blocker
  if (!webSerialSupported) {
    return (
      <div className="device-blocker">
        <div className="device-blocker-content">
          <h1>⚠️ Browser Not Supported</h1>
          <p>This app requires <strong>Chrome</strong> or <strong>Chromium-based browsers</strong> (Edge, Brave, Opera).</p>
          <p>Web Serial API is <strong>not available</strong> in:</p>
          <ul>
            <li>❌ Firefox</li>
            <li>❌ Safari</li>
            <li>❌ Mobile browsers</li>
          </ul>
          <a 
            className="download-button" 
            href="https://www.google.com/chrome/" 
            target="_blank" 
            rel="noreferrer"
          >
            Download Chrome
          </a>
          <p className="muted" style={{ marginTop: "16px" }}>
            {browserConstraintMessage()}
          </p>
        </div>
      </div>
    );
  }

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
          <div className="info-badge" role="status" aria-label={`Version ${appSemver}`}>
            <span className="info-badge-label">Version</span>
            <span className="info-badge-value">v{appSemver}</span>
          </div>
          <a className="info-badge" href="https://github.com/XoniBlue/Baofeng-Logo-Flasher" target="_blank" rel="noreferrer">
            <span className="info-badge-label">Repo</span>
            <span className="info-badge-value">Baofeng-Logo-Flasher</span>
          </a>
        </div>
      </header>

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
        <PortPanel 
          connected={connected} 
          connecting={connecting}
          onConnect={onConnect}
          onDisconnect={onDisconnect}
          disabled={busy} 
        />
        <ImagePanel
          previewUrl={previewUrl}
          selectedFileName={selectedFileName}
          onSelectFile={async (file) => {
            try {
              await onSelectFile(file);
            } catch (imageError) {
              const errorText = friendlyErrorMessage(imageError);
              setError(errorText);
              appendLog(`Image error: ${errorText}`, "error");
            }
          }}
        />
      </div>

      <FlashPanel
        writeMode={writeMode}
        progress={progress}
        operationStatus={operationStatus}
        busy={busy}
        canFlash={canFlash}
        onWriteModeChange={(enabled) => {
          setWriteMode(enabled);
          saveWriteMode(enabled);
        }}
        onFlash={onFlashClick}
      />

      {error ? <div className="error">{error}</div> : null}
      
      {success && !writeMode && (
        <div className="simulation-success">
          <h3>✓ Simulation Complete</h3>
          <p>Frame generation successful. Ready for real flash.</p>
          <p className="muted">Enable Write Mode above to flash your radio.</p>
        </div>
      )}

      {success && writeMode && (
        <div className="flash-complete">
          <h3>✓ Flash Complete!</h3>
          <p><strong>Next steps:</strong></p>
          <ol>
            <li>Turn off your radio completely</li>
            <li>Turn it back on</li>
            <li>Your new logo will display during boot</li>
          </ol>
          <p className="muted">If the logo doesn't appear, try flashing again or check your radio's programming mode.</p>
        </div>
      )}

      <section className="panel">
        <h2>Logs</h2>
        <StatusLog logs={logs} />
      </section>

      {showWriteModal && (
        <ConfirmWriteModal
          model={selectedModel.model}
          onConfirm={() => {
            setShowWriteModal(false);
            void onFlash(true);
          }}
          onCancel={() => {
            setShowWriteModal(false);
            setBusy(false);
          }}
        />
      )}
    </main>
  );
}
