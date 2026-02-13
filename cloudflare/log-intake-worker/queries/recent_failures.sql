SELECT
  received_at_ms,
  occurred_at,
  event_type,
  message,
  error_name,
  origin,
  connected,
  write_mode,
  app_version,
  page_url
FROM client_logs
WHERE
  error_name IS NOT NULL
  OR event_type IN (
    'flash_error',
    'connect_error',
    'unhandled_rejection',
    'window_error',
    'client_error',
    'flash_fail',
    'connect_fail',
    'unhandledrejection'
  )
ORDER BY received_at_ms DESC
LIMIT 50;
