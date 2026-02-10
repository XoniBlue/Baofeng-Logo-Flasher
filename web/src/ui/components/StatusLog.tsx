interface StatusLogProps {
  logs: string[];
}

/** Displays protocol log lines, or placeholder text before activity begins. */
export function StatusLog({ logs }: StatusLogProps): JSX.Element {
  if (logs.length === 0) {
    return <p className="muted">No protocol logs yet.</p>;
  }
  return <pre className="log-box">{logs.join("\n")}</pre>;
}
