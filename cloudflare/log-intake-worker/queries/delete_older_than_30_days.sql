DELETE FROM client_logs
WHERE received_at_ms < (CAST(strftime('%s', 'now', '-30 days') AS INTEGER) * 1000);
