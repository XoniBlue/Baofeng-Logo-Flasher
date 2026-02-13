CREATE TABLE IF NOT EXISTS telemetry_events (
  id TEXT PRIMARY KEY,
  received_at_ms INTEGER NOT NULL,
  occurred_at TEXT NOT NULL,
  event_type TEXT NOT NULL,
  session_id TEXT,
  message TEXT NOT NULL,
  error_name TEXT,
  stack TEXT,
  model TEXT NOT NULL,
  write_mode INTEGER NOT NULL,
  connected INTEGER NOT NULL,
  app_version TEXT NOT NULL,
  log_lines_json TEXT NOT NULL,
  metadata_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_telemetry_events_received_at ON telemetry_events(received_at_ms DESC);
CREATE INDEX IF NOT EXISTS idx_telemetry_events_event_type_received_at ON telemetry_events(event_type, received_at_ms DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_telemetry_success_session_unique
ON telemetry_events(event_type, session_id)
WHERE event_type = 'flash_success' AND session_id IS NOT NULL;
