const LOG_INGEST_URL = (import.meta.env.VITE_LOG_INGEST_URL as string | undefined)?.trim() ?? "";
const TELEMETRY_BASE_URL = (
  (import.meta.env.VITE_TELEMETRY_BASE_URL as string | undefined)?.trim() ??
  ""
).replace(/\/$/, "");
const APP_VERSION = (import.meta.env.VITE_APP_VERSION as string | undefined)?.trim() || "dev";

// Guards against duplicate increments caused by retries or repeated UI events.
const completedSessions = new Set<string>();
const inFlightSessions = new Set<string>();

interface CountResponse {
  total: number;
}

interface UnifiedEventResponse {
  deduped?: boolean;
}

function requireTelemetryBaseUrl(): string {
  if (TELEMETRY_BASE_URL) {
    return TELEMETRY_BASE_URL;
  }
  if (LOG_INGEST_URL) {
    return LOG_INGEST_URL.replace(/\/client-log\/?$/, "").replace(/\/$/, "");
  }
  if (!TELEMETRY_BASE_URL) {
    throw new Error("VITE_TELEMETRY_BASE_URL is required");
  }
  return TELEMETRY_BASE_URL;
}

function trimTo(input: string, maxChars: number): string {
  if (input.length <= maxChars) {
    return input;
  }
  return `${input.slice(0, maxChars - 1)}...`;
}

function sanitizeLogLines(lines: string[]): string[] {
  return lines.slice(-80).map((line) => trimTo(String(line), 240));
}

/** Fetches current global successful flash count from unified telemetry metrics endpoint. */
export async function fetchGlobalFlashCount(): Promise<number> {
  const baseUrl = requireTelemetryBaseUrl();
  const response = await fetch(`${baseUrl}/metrics/flash-count`, {
    method: "GET"
  });
  if (!response.ok) {
    throw new Error(`Counter fetch failed with status ${response.status}`);
  }
  const body = (await response.json()) as CountResponse;
  if (typeof body.total !== "number" || !Number.isFinite(body.total)) {
    throw new Error("Counter fetch returned invalid payload");
  }
  return body.total;
}

/** Records one success event per session and returns updated global success count. */
export async function recordSuccessfulFlashOnce(event: {
  sessionId: string;
  model: string;
  writeMode: boolean;
  connected: boolean;
  logLines?: string[];
}): Promise<number | null> {
  const sessionId = event.sessionId;
  if (!sessionId || completedSessions.has(sessionId) || inFlightSessions.has(sessionId)) {
    return null;
  }

  const baseUrl = requireTelemetryBaseUrl();
  inFlightSessions.add(sessionId);
  try {
    const response = await fetch(`${baseUrl}/event`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        event_type: "flash_success",
        occurred_at: new Date().toISOString(),
        session_id: sessionId,
        message: "Flash complete",
        model: event.model,
        write_mode: event.writeMode ? 1 : 0,
        connected: event.connected ? 1 : 0,
        app_version: APP_VERSION,
        log_lines_json: JSON.stringify(sanitizeLogLines(event.logLines ?? [])),
        metadata_json: JSON.stringify({ source: "web-v2" })
      })
    });
    if (!response.ok) {
      throw new Error(`Success event post failed with status ${response.status}`);
    }

    const body = (await response.json()) as UnifiedEventResponse;
    if (!body.deduped) {
      completedSessions.add(sessionId);
    }

    return await fetchGlobalFlashCount();
  } catch (error) {
    console.error("Flash success telemetry failed:", error);
    return null;
  } finally {
    inFlightSessions.delete(sessionId);
  }
}
