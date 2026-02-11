interface Env {
  LOG_DB: D1Database;
  ALLOWED_ORIGINS?: string;
  ADMIN_TOKEN?: string;
}

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

const MAX_BODY_CHARS = 40_000;
const MAX_LINE_CHARS = 240;
const MAX_STACK_CHARS = 1_200;
const MAX_MESSAGE_CHARS = 300;
const MAX_LOG_LINES = 80;

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
  return `${value.slice(0, maxChars - 1)}…`;
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

function parsePayload(input: unknown): ClientLogInsertPayload | null {
  if (typeof input !== "object" || input === null) {
    return null;
  }
  const p = input as Record<string, unknown>;

  // Required fields only. Unknown/extra fields are intentionally ignored.
  if (typeof p.event_type !== "string" || typeof p.message !== "string" || typeof p.occurred_at !== "string") {
    return null;
  }
  if (!isIsoDateString(p.occurred_at)) {
    return null;
  }

  const parsedLogLinesJson =
    typeof p.log_lines_json === "string"
      ? trimTo(p.log_lines_json, MAX_BODY_CHARS)
      : JSON.stringify([]);

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
    log_lines_json: parsedLogLinesJson,
    origin: null,
    ip_hash: null
  };
}

async function handleIngest(request: Request, env: Env): Promise<Response> {
  const origin = request.headers.get("Origin");
  const allowedOrigin = resolveCorsOrigin(origin, env);
  if (origin && !allowedOrigin) {
    return jsonResponse(403, { ok: false, error: "Origin not allowed" });
  }

  const bodyText = await request.text();
  if (bodyText.length > MAX_BODY_CHARS) {
    return jsonResponse(413, { ok: false, error: "Payload too large" }, corsHeaders(allowedOrigin));
  }

  let parsedJson: unknown;
  try {
    parsedJson = JSON.parse(bodyText);
  } catch {
    return jsonResponse(400, { ok: false, error: "Invalid JSON" }, corsHeaders(allowedOrigin));
  }
  const payload = parsePayload(parsedJson);
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
    logLines: typeof row.log_lines_json === "string" ? (JSON.parse(row.log_lines_json) as string[]) : []
  }));

  return jsonResponse(200, { ok: true, count: rows.length, rows });
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
      return handleIngest(request, env);
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
