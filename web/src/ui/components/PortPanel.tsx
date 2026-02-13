interface PortPanelProps {
  connected: boolean;
  connecting: boolean;
  onConnect: () => Promise<void>;
  onDisconnect: () => Promise<void>;
  disabled: boolean;
}

/** Step 1 UI for requesting Web Serial port access with connect/disconnect toggle. */
export function PortPanel({ 
  connected, 
  connecting, 
  onConnect, 
  onDisconnect, 
  disabled 
}: PortPanelProps): JSX.Element {
  const handleClick = (): void => {
    if (connected) {
      void onDisconnect();
    } else {
      void onConnect();
    }
  };

  return (
    <section className="panel">
      <h2>Step 1 - Serial Connection</h2>
      <p className="muted">Use Chrome and click connect to grant serial access.</p>
      <button disabled={disabled || connecting} onClick={handleClick}>
        {connecting ? (
          <>
            <span className="spinner"></span>
            Connecting...
          </>
        ) : connected ? (
          "✓ Connected - Click to Disconnect"
        ) : (
          "Select serial port"
        )}
      </button>
      
      {connected && !connecting && (
        <p className="muted" style={{ marginTop: '8px', fontSize: '0.85rem' }}>
          Ready to flash. Radio must remain in programming mode.
        </p>
      )}
    </section>
  );
}
