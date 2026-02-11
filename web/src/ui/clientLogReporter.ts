type ClientLogEventType = "flash_error" | "connect_error" | "window_error" | "unhandled_rejection";

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

const LOG_INGEST_URL = (import.meta.env.VITE_LOG_INGEST_URL as string | undefined)?.trim() ?? "";
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
  return `${input.slice(0, maxChars - 1)}…`;
}

function sanitizeLogLines(lines: string[]): string[] {
  return lines.slice(-MAX_LOG_LINES).map((line) => trimTo(String(line), MAX_LINE_CHARS));
}

function fingerprint(payload: ClientLogPayload): string {
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

/** Sends privacy-minimized diagnostics to a Cloudflare Worker endpoint when enabled. */
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
  if (!LOG_INGEST_URL) {
    return;
  }

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
    // Intentionally blank to avoid collecting browser/device fingerprints.
    user_agent: "",
    // Intentionally blank to avoid storing path/query fragments.
    page_url: "",
    log_lines_json: JSON.stringify(sanitizeLogLines(event.logLines ?? []))
  };

  const fingerprintKey = fingerprint(payload);
  const nowMs = Date.now();
  if (!shouldSend(fingerprintKey, nowMs)) {
    return;
  }

  const body = JSON.stringify(payload);
  const sendWithFetch = async (): Promise<void> => {
    await fetch(LOG_INGEST_URL, {
      method: "POST",
      mode: "cors",
      keepalive: true,
      headers: {
        "Content-Type": "application/json"
      },
      body
    });
  };

  // Prefer fetch for normal runtime visibility; use sendBeacon only on hidden page.
  if (document.visibilityState === "hidden" && typeof navigator.sendBeacon === "function") {
    const blob = new Blob([body], { type: "application/json" });
    navigator.sendBeacon(LOG_INGEST_URL, blob);
    return;
  }

  void sendWithFetch().catch(() => {
    // Telemetry must never break flashing flow.
  });
}
