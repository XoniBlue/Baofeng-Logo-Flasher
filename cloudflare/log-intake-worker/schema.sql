CREATE TABLE IF NOT EXISTS client_logs (
  id TEXT PRIMARY KEY,
  received_at_ms INTEGER NOT NULL,
  occurred_at TEXT NOT NULL,
  event_type TEXT NOT NULL,
  message TEXT NOT NULL,
  error_name TEXT,
  stack TEXT,
  model TEXT NOT NULL,
  write_mode INTEGER NOT NULL,
  connected INTEGER NOT NULL,
  app_version TEXT NOT NULL,
  user_agent TEXT NOT NULL,
  page_url TEXT NOT NULL,
  log_lines_json TEXT NOT NULL,
  origin TEXT,
  ip_hash TEXT
);

CREATE INDEX IF NOT EXISTS idx_client_logs_received_at ON client_logs(received_at_ms DESC);
CREATE INDEX IF NOT EXISTS idx_client_logs_event_type ON client_logs(event_type);
