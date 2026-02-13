import React from "react";
import type { LogEntry } from "../../App";

interface StatusLogProps {
  logs: LogEntry[];
}

/** Displays color-coded protocol log lines with auto-scroll, or placeholder before activity begins. */
export function StatusLog({ logs }: StatusLogProps): JSX.Element {
  const logBoxRef = React.useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new logs arrive
  React.useEffect(() => {
    if (logBoxRef.current) {
      logBoxRef.current.scrollTop = logBoxRef.current.scrollHeight;
    }
  }, [logs]);

  if (logs.length === 0) {
    return <p className="muted">No protocol logs yet.</p>;
  }

  return (
    <div className="log-box" ref={logBoxRef}>
      {logs.map((log, index) => (
        <div key={index} className={`log-entry log-${log.level}`}>
          <span className="log-timestamp">[{log.timestamp}]</span>
          <span className="log-message">{log.message}</span>
        </div>
      ))}
    </div>
  );
}
