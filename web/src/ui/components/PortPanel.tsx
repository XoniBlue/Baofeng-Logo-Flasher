interface PortPanelProps {
  connected: boolean;
  onConnect: () => Promise<void>;
  disabled: boolean;
}

export function PortPanel({ connected, onConnect, disabled }: PortPanelProps): JSX.Element {
  return (
    <section className="panel">
      <h2>Step 1 - Serial Connection</h2>
      <p className="muted">Use Chrome and click connect to grant serial access.</p>
      <button disabled={disabled} onClick={() => void onConnect()}>
        {connected ? "Port selected" : "Select serial port"}
      </button>
    </section>
  );
}
