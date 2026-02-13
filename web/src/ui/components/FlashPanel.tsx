interface FlashPanelProps {
  writeMode: boolean;
  progress: number;
  operationStatus: string;
  busy: boolean;
  canFlash: boolean;
  onWriteModeChange: (enabled: boolean) => void;
  onFlash: () => void;
}

/** Step 3 UI for write-mode controls and upload/simulation trigger with operation status. */
export function FlashPanel({
  writeMode,
  progress,
  operationStatus,
  busy,
  canFlash,
  onWriteModeChange,
  onFlash
}: FlashPanelProps): JSX.Element {
  return (
    <section className="panel">
      <h2>Step 3 - Flash</h2>
      <label className="inline-check">
        <input
          type="checkbox"
          checked={writeMode}
          onChange={(event) => onWriteModeChange(event.currentTarget.checked)}
          disabled={busy}
        />
        Write mode (unchecked = simulation only)
      </label>
      
      {operationStatus && <div className="operation-status">{operationStatus}</div>}
      
      <progress value={progress} max={100} />
      
      <button disabled={busy || !canFlash} onClick={onFlash}>
        {busy ? (
          <>
            <span className="spinner"></span>
            {writeMode ? "Flashing..." : "Simulating..."}
          </>
        ) : (
          writeMode ? "Flash logo" : "Simulate"
        )}
      </button>
    </section>
  );
}
