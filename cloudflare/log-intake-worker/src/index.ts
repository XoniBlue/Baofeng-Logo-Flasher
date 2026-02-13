interface Env {
  LOG_DB: D1Database;
  ALLOWED_ORIGINS?: string;
  ADMIN_TOKEN?: string;
}

type UnifiedEventType =
  | "flash_success"
  | "flash_error"
  | "connect_error"
  | "window_error"
  | "unhandled_rejection"
  | "client_error";

interface ClientLogInsertPayload {
  event_type: string;
  occurred_at: string;
  message: string;
  error_name: string | null;
  stack: string | null;
  model: string;
  write_mode: number;
  connected: number;
  app_version: string;
  user_agent: string;
  page_url: string;
  log_lines_json: string;
  origin: string | null;
  ip_hash: string | null;
}

interface UnifiedTelemetryInsertPayload {
  event_type: UnifiedEventType;
  occurred_at: string;
  message: string;
  session_id: string | null;
  error_name: string | null;
  stack: string | null;
  model: string;
  write_mode: number;
  connected: number;
  app_version: string;
  log_lines_json: string;
  metadata_json: string;
}

const MAX_BODY_CHARS = 40_000;
const MAX_LINE_CHARS = 240;
const MAX_STACK_CHARS = 1_200;
const MAX_MESSAGE_CHARS = 300;
const MAX_LOG_LINES = 80;
const MAX_SESSION_ID_CHARS = 120;
const ALLOWED_UNIFIED_EVENTS = new Set<UnifiedEventType>([
  "flash_success",
  "flash_error",
  "connect_error",
  "window_error",
  "unhandled_rejection",
  "client_error"
]);

function jsonResponse(status: number, body: unknown, extraHeaders?: HeadersInit): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      ...extraHeaders
    }
  });
}

function parseAllowedOrigins(env: Env): string[] {
  if (!env.ALLOWED_ORIGINS?.trim()) {
    return ["https://xoniblue.github.io", "http://localhost:5173", "http://127.0.0.1:5173"];
  }
  return env.ALLOWED_ORIGINS.split(",")
    .map((origin) => origin.trim())
    .filter((origin) => origin.length > 0);
}

function resolveCorsOrigin(requestOrigin: string | null, env: Env): string | null {
  if (!requestOrigin) {
    return null;
  }
  const allowed = parseAllowedOrigins(env);
  return allowed.includes(requestOrigin) ? requestOrigin : null;
}

function corsHeaders(origin: string | null): HeadersInit {
  if (!origin) {
    return {};
  }
  return {
    "Access-Control-Allow-Origin": origin,
    "Vary": "Origin",
    "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
    "Access-Control-Max-Age": "86400"
  };
}

function trimTo(value: string, maxChars: number): string {
  if (value.length <= maxChars) {
    return value;
  }
  return `${value.slice(0, maxChars - 1)}...`;
}

function asNullableString(value: unknown, maxChars: number): string | null {
  if (value === null || typeof value === "undefined") {
    return null;
  }
  if (typeof value !== "string") {
    return null;
  }
  return trimTo(value, maxChars);
}

function asOptionalStringOrDefault(value: unknown, maxChars: number, fallback: string): string {
  if (typeof value !== "string" || value.length === 0) {
    return fallback;
  }
  return trimTo(value, maxChars);
}

function asNumber01(value: unknown, fallback: number): number {
  if (value === 0 || value === 1) {
    return value;
  }
  return fallback;
}

function isIsoDateString(value: string): boolean {
  const parsed = Date.parse(value);
  return Number.isFinite(parsed);
}

function sanitizeLogLinesJson(value: unknown): string {
  if (typeof value !== "string") {
    return "[]";
  }
  try {
    const parsed = JSON.parse(value);
    if (!Array.isArray(parsed)) {
      return "[]";
    }
    const lines = parsed.slice(-MAX_LOG_LINES).map((line) => trimTo(String(line), MAX_LINE_CHARS));
    return JSON.stringify(lines);
  } catch {
    return "[]";
  }
}

function sanitizeMetadataJson(value: unknown): string {
  if (typeof value !== "string") {
    return "{}";
  }
  try {
    const parsed = JSON.parse(value);
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      return "{}";
    }
    const serialized = JSON.stringify(parsed);
    if (serialized.length > MAX_BODY_CHARS) {
      return "{}";
    }
    return serialized;
  } catch {
    return "{}";
  }
}

function parseLegacyPayload(input: unknown): ClientLogInsertPayload | null {
  if (typeof input !== "object" || input === null) {
    return null;
  }
  const p = input as Record<string, unknown>;

  if (typeof p.event_type !== "string" || typeof p.message !== "string" || typeof p.occurred_at !== "string") {
    return null;
  }
  if (!isIsoDateString(p.occurred_at)) {
    return null;
  }

  return {
    event_type: trimTo(p.event_type, 40),
    occurred_at: trimTo(p.occurred_at, 64),
    message: trimTo(p.message, MAX_MESSAGE_CHARS),
    error_name: asNullableString(p.error_name, 120),
    stack: asNullableString(p.stack, MAX_STACK_CHARS),
    model: asOptionalStringOrDefault(p.model, 64, "unknown"),
    write_mode: asNumber01(p.write_mode, 0),
    connected: asNumber01(p.connected, 0),
    app_version: asOptionalStringOrDefault(p.app_version, 64, "unknown"),
    user_agent: "",
    page_url: "",
    log_lines_json: sanitizeLogLinesJson(p.log_lines_json),
    origin: null,
    ip_hash: null
  };
}

function parseUnifiedPayload(input: unknown): UnifiedTelemetryInsertPayload | null {
  if (typeof input !== "object" || input === null) {
    return null;
  }
  const p = input as Record<string, unknown>;

  if (typeof p.event_type !== "string" || typeof p.message !== "string" || typeof p.occurred_at !== "string") {
    return null;
  }
  if (!ALLOWED_UNIFIED_EVENTS.has(p.event_type as UnifiedEventType)) {
    return null;
  }
  if (!isIsoDateString(p.occurred_at)) {
    return null;
  }

  const sessionId = asNullableString(p.session_id, MAX_SESSION_ID_CHARS);
  if (p.event_type === "flash_success" && !sessionId) {
    return null;
  }

  return {
    event_type: p.event_type as UnifiedEventType,
    occurred_at: trimTo(p.occurred_at, 64),
    message: trimTo(p.message, MAX_MESSAGE_CHARS),
    session_id: sessionId,
    error_name: asNullableString(p.error_name, 120),
    stack: asNullableString(p.stack, MAX_STACK_CHARS),
    model: asOptionalStringOrDefault(p.model, 64, "unknown"),
    write_mode: asNumber01(p.write_mode, 0),
    connected: asNumber01(p.connected, 0),
    app_version: asOptionalStringOrDefault(p.app_version, 64, "unknown"),
    log_lines_json: sanitizeLogLinesJson(p.log_lines_json),
    metadata_json: sanitizeMetadataJson(p.metadata_json)
  };
}

async function parseRequestJson(request: Request): Promise<{ ok: true; value: unknown } | { ok: false; response: Response }> {
  const bodyText = await request.text();
  if (bodyText.length > MAX_BODY_CHARS) {
    return { ok: false, response: jsonResponse(413, { ok: false, error: "Payload too large" }) };
  }

  try {
    return { ok: true, value: JSON.parse(bodyText) };
  } catch {
    return { ok: false, response: jsonResponse(400, { ok: false, error: "Invalid JSON" }) };
  }
}

async function handleLegacyIngest(request: Request, env: Env): Promise<Response> {
  const origin = request.headers.get("Origin");
  const allowedOrigin = resolveCorsOrigin(origin, env);
  if (origin && !allowedOrigin) {
    return jsonResponse(403, { ok: false, error: "Origin not allowed" });
  }

  const parsed = await parseRequestJson(request);
  if (!parsed.ok) {
    return jsonResponse(parsed.response.status, await parsed.response.json(), corsHeaders(allowedOrigin));
  }

  const payload = parseLegacyPayload(parsed.value);
  if (!payload) {
    return jsonResponse(400, { ok: false, error: "Invalid payload fields" }, corsHeaders(allowedOrigin));
  }

  const nowMs = Date.now();
  const rowId = crypto.randomUUID();

  await env.LOG_DB.prepare(
    `
      INSERT INTO client_logs (
        id,
        received_at_ms,
        occurred_at,
        event_type,
        message,
        error_name,
        stack,
        model,
        write_mode,
        connected,
        app_version,
        user_agent,
        page_url,
        log_lines_json,
        origin,
        ip_hash
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `
  )
    .bind(
      rowId,
      nowMs,
      payload.occurred_at,
      payload.event_type,
      payload.message,
      payload.error_name,
      payload.stack ?? null,
      payload.model,
      payload.write_mode,
      payload.connected,
      payload.app_version,
      payload.user_agent,
      payload.page_url,
      payload.log_lines_json,
      payload.origin,
      payload.ip_hash
    )
    .run();

  return jsonResponse(200, { ok: true }, corsHeaders(allowedOrigin));
}

async function handleUnifiedIngest(request: Request, env: Env): Promise<Response> {
  const origin = request.headers.get("Origin");
  const allowedOrigin = resolveCorsOrigin(origin, env);
  if (origin && !allowedOrigin) {
    return jsonResponse(403, { ok: false, error: "Origin not allowed" });
  }

  const parsed = await parseRequestJson(request);
  if (!parsed.ok) {
    return jsonResponse(parsed.response.status, await parsed.response.json(), corsHeaders(allowedOrigin));
  }

  const payload = parseUnifiedPayload(parsed.value);
  if (!payload) {
    return jsonResponse(400, { ok: false, error: "Invalid payload fields" }, corsHeaders(allowedOrigin));
  }

  const nowMs = Date.now();
  const rowId = crypto.randomUUID();
  const result = await env.LOG_DB.prepare(
    `
      INSERT OR IGNORE INTO telemetry_events (
        id,
        received_at_ms,
        occurred_at,
        event_type,
        session_id,
        message,
        error_name,
        stack,
        model,
        write_mode,
        connected,
        app_version,
        log_lines_json,
        metadata_json
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `
  )
    .bind(
      rowId,
      nowMs,
      payload.occurred_at,
      payload.event_type,
      payload.session_id,
      payload.message,
      payload.error_name,
      payload.stack,
      payload.model,
      payload.write_mode,
      payload.connected,
      payload.app_version,
      payload.log_lines_json,
      payload.metadata_json
    )
    .run();

  const changed = Number(result.meta?.changes ?? 0) > 0;
  return jsonResponse(200, { ok: true, deduped: !changed }, corsHeaders(allowedOrigin));
}

function safeParseLogLines(value: unknown): string[] {
  if (typeof value !== "string") {
    return [];
  }
  try {
    const parsed = JSON.parse(value);
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed.map((line) => String(line));
  } catch {
    return [];
  }
}

async function handleRecent(request: Request, env: Env): Promise<Response> {
  if (!env.ADMIN_TOKEN?.trim()) {
    return jsonResponse(503, { ok: false, error: "ADMIN_TOKEN is not configured" });
  }
  const authHeader = request.headers.get("Authorization") ?? "";
  const token = authHeader.startsWith("Bearer ") ? authHeader.slice("Bearer ".length).trim() : "";
  if (!token || token !== env.ADMIN_TOKEN) {
    return jsonResponse(401, { ok: false, error: "Unauthorized" });
  }

  const url = new URL(request.url);
  const requestedLimit = Number(url.searchParams.get("limit") ?? "50");
  const limit = Number.isFinite(requestedLimit) ? Math.min(200, Math.max(1, Math.floor(requestedLimit))) : 50;

  const result = await env.LOG_DB.prepare(
    `
      SELECT
        id,
        received_at_ms,
        occurred_at,
        event_type,
        message,
        error_name,
        model,
        write_mode,
        connected,
        app_version,
        page_url,
        log_lines_json
      FROM client_logs
      ORDER BY received_at_ms DESC
      LIMIT ?
    `
  )
    .bind(limit)
    .all<Record<string, unknown>>();

  const rows = (result.results ?? []).map((row) => ({
    id: row.id,
    receivedAtMs: row.received_at_ms,
    occurredAt: row.occurred_at,
    eventType: row.event_type,
    message: row.message,
    errorName: row.error_name,
    model: row.model,
    writeMode: row.write_mode === 1,
    connected: row.connected === 1,
    appVersion: row.app_version,
    pageUrl: row.page_url,
    logLines: safeParseLogLines(row.log_lines_json)
  }));

  return jsonResponse(200, { ok: true, count: rows.length, rows });
}

async function handleFlashCount(request: Request, env: Env): Promise<Response> {
  const origin = request.headers.get("Origin");
  const allowedOrigin = resolveCorsOrigin(origin, env);
  if (origin && !allowedOrigin) {
    return jsonResponse(403, { ok: false, error: "Origin not allowed" });
  }

  const result = await env.LOG_DB.prepare(
    `
      SELECT COUNT(*) AS total
      FROM telemetry_events
      WHERE event_type = 'flash_success'
        AND (session_id IS NULL OR session_id NOT LIKE 'baseline-%')
    `
  ).all<Record<string, unknown>>();

  const baselineResult = await env.LOG_DB.prepare(
    `
      SELECT
        COALESCE(MAX(CAST(json_extract(metadata_json, '$.baseline_total') AS INTEGER)), 0) AS baseline_total
      FROM telemetry_events
      WHERE event_type = 'flash_success'
        AND session_id LIKE 'baseline-%'
    `
  ).all<Record<string, unknown>>();

  const row = result.results?.[0];
  const baselineRow = baselineResult.results?.[0];
  const liveTotal = Math.max(0, Math.floor(Number(row?.total ?? 0)));
  const baselineTotal = Math.max(0, Math.floor(Number(baselineRow?.baseline_total ?? 0)));
  const total = liveTotal + baselineTotal;
  return jsonResponse(200, { ok: true, total }, corsHeaders(allowedOrigin));
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const origin = request.headers.get("Origin");
    const allowedOrigin = resolveCorsOrigin(origin, env);

    if (request.method === "OPTIONS") {
      if (origin && !allowedOrigin) {
        return new Response(null, { status: 403 });
      }
      return new Response(null, { status: 204, headers: corsHeaders(allowedOrigin) });
    }

    if (request.method === "POST" && url.pathname === "/client-log") {
      return handleLegacyIngest(request, env);
    }
    if (request.method === "POST" && url.pathname === "/event") {
      return handleUnifiedIngest(request, env);
    }
    if (request.method === "GET" && url.pathname === "/metrics/flash-count") {
      return handleFlashCount(request, env);
    }
    if (request.method === "GET" && url.pathname === "/recent") {
      return handleRecent(request, env);
    }
    if (request.method === "GET" && url.pathname === "/health") {
      return jsonResponse(200, { ok: true, service: "baofeng-log-intake" }, corsHeaders(allowedOrigin));
    }

    return jsonResponse(404, { ok: false, error: "Not found" }, corsHeaders(allowedOrigin));
  }
};
