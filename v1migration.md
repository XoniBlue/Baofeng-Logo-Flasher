# V1 Telemetry Migration Plan (Cloudflare)

## Goal
Unify successful-flash and error telemetry into one Cloudflare Worker + D1 pipeline, while keeping existing UI behavior and avoiding analytics regressions.

## Why migrate
- Current success tracking and error logging use different endpoints and contracts.
- Success counter URL is hardcoded in `web/src/ui/flashCounter.ts`.
- Error telemetry is env-driven and persisted in D1 (`cloudflare/log-intake-worker/src/index.ts`).
- A single telemetry pipeline reduces drift, duplicate infra, and operational overhead.

## Current-state summary
- Success path:
  - `GET /count` and `POST /increment` against `COUNTER_BASE_URL` in `web/src/ui/flashCounter.ts`.
  - Client-side dedupe only (`completedSessions`, `inFlightSessions`).
- Error path:
  - `POST /client-log` via `VITE_LOG_INGEST_URL` in `web/src/ui/clientLogReporter.ts`.
  - Worker validates + writes to D1 `client_logs`.

## Target-state summary
- Single ingest endpoint on the existing Worker, e.g. `POST /event`.
- Event envelope with strict event type:
  - `flash_success`, `flash_error`, `connect_error`, `window_error`, `unhandled_rejection`.
- Server-side idempotency key support for success events.
- Backward compatibility for legacy `/client-log` and existing counter routes during transition.
- One query surface for recent failures and aggregate success metrics.

## Phase plan

### Phase 0: Guardrails (no behavior change)
1. Add a schema migration table and versioned SQL files.
2. Add Worker test harness for ingest/auth/CORS/validation.
3. Keep existing endpoints unchanged.

### Phase 1: Introduce unified event schema
1. Add D1 table `telemetry_events`:
   - `id TEXT PRIMARY KEY`
   - `received_at_ms INTEGER NOT NULL`
   - `occurred_at TEXT NOT NULL`
   - `event_type TEXT NOT NULL`
   - `session_id TEXT`
   - `model TEXT NOT NULL`
   - `write_mode INTEGER NOT NULL`
   - `connected INTEGER NOT NULL`
   - `app_version TEXT NOT NULL`
   - `message TEXT NOT NULL`
   - `error_name TEXT`
   - `stack TEXT`
   - `log_lines_json TEXT NOT NULL`
   - `metadata_json TEXT NOT NULL`
2. Add indexes:
   - `(event_type, received_at_ms DESC)`
   - `(received_at_ms DESC)`
   - unique `(event_type, session_id)` where `session_id IS NOT NULL`.
3. Add endpoint `POST /event` with strict validation.

### Phase 2: Client dual-write and parity checks
1. Keep existing success and error calls, but also write to `/event`.
2. Compare:
   - success totals (`/count`) vs `COUNT(event_type='flash_success')`
   - recent failures old table vs new event stream.
3. Validate no significant drop in ingest success.

### Phase 3: Switch reads
1. Move UI flash counter read to new aggregate endpoint (e.g. `GET /metrics/flash-count`).
2. Move admin recent failures query to new table/views.
3. Keep old endpoints as compatibility aliases.

### Phase 4: Remove legacy paths
1. Remove hardcoded counter URL usage from `web/src/ui/flashCounter.ts`.
2. Remove deprecated routes and old tables once parity window is complete.
3. Finalize docs and runbook.

## API contract proposal

### POST /event
Request body (example):
```json
{
  "event_type": "flash_success",
  "occurred_at": "2026-02-12T18:00:00.000Z",
  "session_id": "uuid-v4",
  "message": "Flash complete",
  "model": "UV-5RM",
  "write_mode": 1,
  "connected": 1,
  "app_version": "<git-sha>",
  "log_lines_json": "[]",
  "metadata_json": "{}"
}
```

### GET /metrics/flash-count
Response:
```json
{ "ok": true, "total": 1234 }
```

## Validation rules
- `event_type` must be enum.
- `occurred_at` must parse as ISO date.
- `write_mode`/`connected` must be `0|1`.
- `message` length-limited and non-empty.
- `session_id` required for `flash_success`.
- `log_lines_json` and `metadata_json` must parse as JSON objects/arrays under size limits.

## Rollback strategy
- Feature flag the unified endpoint usage with `VITE_TELEMETRY_UNIFIED=1`.
- Keep legacy routes active until 7-14 days of parity passes.
- If regressions occur, disable the flag and continue with legacy routes.

## Risks and mitigations
- Risk: double-counting successes during dual-write.
  - Mitigation: server-side unique key `(event_type, session_id)`.
- Risk: ingest abuse from public endpoint.
  - Mitigation: strict CORS + optional signed token + rate limits.
- Risk: schema/query drift.
  - Mitigation: migration files + test coverage for SQL queries.

## Done criteria
- No hardcoded telemetry/counter Worker URL in frontend.
- One Worker handles success + error events.
- Success counter and error feeds sourced from unified event storage.
- CI includes Worker tests and schema migration verification.
