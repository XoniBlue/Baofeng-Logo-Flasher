type ClientLogEventType = "flash_error" | "connect_error" | "window_error" | "unhandled_rejection";
type UnifiedTelemetryEventType = ClientLogEventType | "flash_success";

interface ClientLogPayload {
  event_type: ClientLogEventType;
  occurred_at: string;
  message: string;
  error_name?: string;
  stack?: string;
  model: string;
  write_mode: number;
  connected: number;
  app_version: string;
  user_agent: string;
  page_url: string;
  log_lines_json: string;
}

interface UnifiedTelemetryPayload {
  event_type: UnifiedTelemetryEventType;
  occurred_at: string;
  message: string;
  session_id?: string;
  error_name?: string;
  stack?: string;
  model: string;
  write_mode: number;
  connected: number;
  app_version: string;
  log_lines_json: string;
  metadata_json: string;
}

const LOG_INGEST_URL = (import.meta.env.VITE_LOG_INGEST_URL as string | undefined)?.trim() ?? "";
const TELEMETRY_BASE_URL = ((import.meta.env.VITE_TELEMETRY_BASE_URL as string | undefined)?.trim() ?? "").replace(/\/$/, "");
const TELEMETRY_UNIFIED_ENABLED = (import.meta.env.VITE_TELEMETRY_UNIFIED as string | undefined)?.trim() === "1";
const APP_VERSION = (import.meta.env.VITE_APP_VERSION as string | undefined)?.trim() || "dev";
const RECENT_DEDUP_WINDOW_MS = 15_000;
const MAX_LOG_LINES = 80;
const MAX_LINE_CHARS = 240;
const MAX_MESSAGE_CHARS = 300;
const MAX_STACK_CHARS = 1200;

const recentFingerprints = new Map<string, number>();

function trimTo(input: string, maxChars: number): string {
  if (input.length <= maxChars) {
    return input;
  }
  return `${input.slice(0, maxChars - 1)}...`;
}

function sanitizeLogLines(lines: string[]): string[] {
  return lines.slice(-MAX_LOG_LINES).map((line) => trimTo(String(line), MAX_LINE_CHARS));
}

function fingerprint(payload: Pick<ClientLogPayload, "event_type" | "model" | "message"> & { stack?: string }): string {
  return [payload.event_type, payload.model, payload.message, payload.stack ?? ""].join("|");
}

function shouldSend(fingerprintKey: string, nowMs: number): boolean {
  const lastSentMs = recentFingerprints.get(fingerprintKey);
  if (typeof lastSentMs === "number" && nowMs - lastSentMs < RECENT_DEDUP_WINDOW_MS) {
    return false;
  }
  recentFingerprints.set(fingerprintKey, nowMs);
  for (const [key, seenAt] of recentFingerprints.entries()) {
    if (nowMs - seenAt > RECENT_DEDUP_WINDOW_MS) {
      recentFingerprints.delete(key);
    }
  }
  return true;
}

function sendBody(url: string, body: string): void {
  if (!url) {
    return;
  }

  if (document.visibilityState === "hidden" && typeof navigator.sendBeacon === "function") {
    const blob = new Blob([body], { type: "application/json" });
    navigator.sendBeacon(url, blob);
    return;
  }

  void fetch(url, {
    method: "POST",
    mode: "cors",
    keepalive: true,
    headers: {
      "Content-Type": "application/json"
    },
    body
  }).catch(() => {
    // Telemetry must never break flashing flow.
  });
}

function sendUnifiedEvent(payload: UnifiedTelemetryPayload): void {
  if (!TELEMETRY_UNIFIED_ENABLED || !TELEMETRY_BASE_URL) {
    return;
  }
  sendBody(`${TELEMETRY_BASE_URL}/event`, JSON.stringify(payload));
}

/** Sends privacy-minimized diagnostics to configured Cloudflare endpoints. */
export function reportClientError(event: {
  eventType: ClientLogEventType;
  message: string;
  errorName?: string;
  stack?: string;
  model: string;
  writeMode: boolean;
  connected: boolean;
  logLines?: string[];
}): void {
  const logLinesJson = JSON.stringify(sanitizeLogLines(event.logLines ?? []));
  const payload: ClientLogPayload = {
    event_type: event.eventType,
    occurred_at: new Date().toISOString(),
    message: trimTo(String(event.message), MAX_MESSAGE_CHARS),
    error_name: event.errorName ? trimTo(String(event.errorName), 120) : undefined,
    stack: event.stack ? trimTo(String(event.stack), MAX_STACK_CHARS) : undefined,
    model: event.model,
    write_mode: event.writeMode ? 1 : 0,
    connected: event.connected ? 1 : 0,
    app_version: APP_VERSION,
    user_agent: "",
    page_url: "",
    log_lines_json: logLinesJson
  };

  const fingerprintKey = fingerprint(payload);
  const nowMs = Date.now();
  if (!shouldSend(fingerprintKey, nowMs)) {
    return;
  }

  if (LOG_INGEST_URL) {
    sendBody(LOG_INGEST_URL, JSON.stringify(payload));
  }

  sendUnifiedEvent({
    event_type: payload.event_type,
    occurred_at: payload.occurred_at,
    message: payload.message,
    error_name: payload.error_name,
    stack: payload.stack,
    model: payload.model,
    write_mode: payload.write_mode,
    connected: payload.connected,
    app_version: payload.app_version,
    log_lines_json: payload.log_lines_json,
    metadata_json: JSON.stringify({ source: "web-v2" })
  });
}

/** Emits a unified success event used for migration parity and future unified metrics. */
export function reportFlashSuccess(event: {
  sessionId: string;
  model: string;
  writeMode: boolean;
  connected: boolean;
  logLines?: string[];
}): void {
  if (!event.sessionId) {
    return;
  }

  const nowIso = new Date().toISOString();
  const message = "Flash complete";
  const logLinesJson = JSON.stringify(sanitizeLogLines(event.logLines ?? []));
  const payload: UnifiedTelemetryPayload = {
    event_type: "flash_success",
    occurred_at: nowIso,
    session_id: event.sessionId,
    message,
    model: event.model,
    write_mode: event.writeMode ? 1 : 0,
    connected: event.connected ? 1 : 0,
    app_version: APP_VERSION,
    log_lines_json: logLinesJson,
    metadata_json: JSON.stringify({ source: "web-v2" })
  };

  const fingerprintKey = [payload.event_type, payload.session_id, payload.model].join("|");
  const nowMs = Date.now();
  if (!shouldSend(fingerprintKey, nowMs)) {
    return;
  }

  sendUnifiedEvent(payload);
}
