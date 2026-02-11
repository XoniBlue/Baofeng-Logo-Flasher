#!/usr/bin/env node

function parseLimit(argv) {
  const limitFlagIndex = argv.indexOf("--limit");
  if (limitFlagIndex >= 0 && argv[limitFlagIndex + 1]) {
    const parsed = Number(argv[limitFlagIndex + 1]);
    if (Number.isFinite(parsed) && parsed > 0) {
      return Math.min(200, Math.floor(parsed));
    }
  }
  return 20;
}

function normalizeBaseUrl(raw) {
  const trimmed = (raw ?? "").trim();
  if (!trimmed) {
    return "";
  }
  const withoutClientLog = trimmed.replace(/\/client-log\/?$/, "");
  return withoutClientLog.replace(/\/$/, "");
}

function toIsoFromMs(value) {
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) {
    return "";
  }
  return new Date(n).toISOString();
}

const adminToken = (process.env.ADMIN_TOKEN ?? "").trim();
const baseUrl = normalizeBaseUrl(process.env.LOG_WORKER_BASE_URL ?? process.env.LOG_WORKER_URL);
const limit = parseLimit(process.argv.slice(2));
const asJson = process.argv.includes("--json");

if (!adminToken) {
  console.error("Missing ADMIN_TOKEN env var.");
  console.error("Example: ADMIN_TOKEN=... LOG_WORKER_BASE_URL=https://<worker>.workers.dev npm run recent");
  process.exit(1);
}

if (!baseUrl) {
  console.error("Missing LOG_WORKER_BASE_URL (or LOG_WORKER_URL) env var.");
  console.error("Example: LOG_WORKER_BASE_URL=https://<worker>.workers.dev");
  process.exit(1);
}

const url = `${baseUrl}/recent?limit=${limit}`;

const response = await fetch(url, {
  method: "GET",
  headers: {
    Authorization: `Bearer ${adminToken}`
  }
});

if (!response.ok) {
  const bodyText = await response.text();
  console.error(`Request failed: ${response.status} ${response.statusText}`);
  if (bodyText) {
    console.error(bodyText);
  }
  process.exit(1);
}

const body = await response.json();
if (asJson) {
  console.log(JSON.stringify(body, null, 2));
  process.exit(0);
}

const rows = Array.isArray(body?.rows) ? body.rows : [];
if (rows.length === 0) {
  console.log("No rows.");
  process.exit(0);
}

for (const row of rows) {
  const line = [
    toIsoFromMs(row.receivedAtMs),
    String(row.eventType ?? ""),
    String(row.model ?? ""),
    String(row.message ?? "")
  ].join(" | ");
  console.log(line);
}
