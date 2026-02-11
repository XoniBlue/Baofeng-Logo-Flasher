interface FlashPanelProps {
  writeMode: boolean;
  progress: number;
  busy: boolean;
  canFlash: boolean;
  onWriteModeChange: (enabled: boolean) => void;
  onFlash: () => Promise<void>;
}

/** Step 3 UI for write-mode controls and upload/simulation trigger. */
export function FlashPanel({
  writeMode,
  progress,
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
        />
        Write mode (unchecked = simulation only)
      </label>
      <progress value={progress} max={100} />
      <button disabled={busy || !canFlash} onClick={() => void onFlash()}>
        {busy ? "Working..." : writeMode ? "Flash logo" : "Simulate"}
      </button>
    </section>
  );
}
