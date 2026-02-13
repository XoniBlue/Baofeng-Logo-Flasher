# Cloudflare Log Intake Worker

This Worker accepts privacy-minimized client diagnostics from the web flasher and stores them in D1.

Data collection policy:
- Logs error events only (`flash_error`, `connect_error`, `window_error`, `unhandled_rejection`).
- Does not store uploaded image data or serial frame binary data.
- Does not store user-agent, page URL path/query, request origin, or IP-derived fields.

## Endpoints

- `POST /client-log`: ingest client error logs from the web app.
- `POST /event`: unified telemetry ingest (`flash_success` + error events).
- `GET /health`: basic health check.
- `GET /recent?limit=50`: returns recent logs (requires `Authorization: Bearer <ADMIN_TOKEN>`).
- `GET /metrics/flash-count`: returns total `flash_success` event count.

## Local setup

```bash
cd cloudflare/log-intake-worker
npm ci
```

## Cloudflare setup

1. Create D1 database:

```bash
wrangler d1 create baofeng_logs
```

2. Put returned `database_id` into `wrangler.toml` (`database_id = "..."`).

3. Apply schema:

```bash
wrangler d1 execute baofeng_logs --file ./schema.sql --remote
wrangler d1 execute baofeng_logs --file ./migrations/001_telemetry_events.sql --remote
```

4. Configure Worker secrets:

```bash
wrangler secret put ADMIN_TOKEN
```

Set `ALLOWED_ORIGINS` as a Worker var in `wrangler.toml`:

```text
[vars]
ALLOWED_ORIGINS = "https://xoniblue.github.io,http://localhost:5173,http://127.0.0.1:5173"
```

5. Deploy Worker:

```bash
npm run deploy
```

6. Copy deployed Worker URL and append `/client-log`. Example:

```text
https://baofeng-log-intake.<subdomain>.workers.dev/client-log
```

## Inspect logs

Option 1: query D1 directly:

```bash
wrangler d1 execute baofeng_logs --remote --file ./queries/recent_failures.sql
```

Option 2: read through API:

```bash
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  "https://baofeng-log-intake.<subdomain>.workers.dev/recent?limit=50"
```

Option 3: helper command:

```bash
ADMIN_TOKEN=<your_admin_token> \
LOG_WORKER_BASE_URL=https://baofeng-log-intake.<subdomain>.workers.dev \
npm run recent -- --limit 20
```

Add `--json` to print full JSON response.

## Retention cleanup

Delete logs older than 30 days:

```bash
npm run retention:30d
```
