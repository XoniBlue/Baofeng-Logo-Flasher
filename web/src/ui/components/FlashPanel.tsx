interface FlashPanelProps {
  writeMode: boolean;
  handshakeProfile: "normal" | "conservative";
  progress: number;
  busy: boolean;
  canFlash: boolean;
  onWriteModeChange: (enabled: boolean) => void;
  onHandshakeProfileChange: (profile: "normal" | "conservative") => void;
  onFlash: () => Promise<void>;
}

/** Step 3 UI for write-mode controls and upload/simulation trigger. */
export function FlashPanel({
  writeMode,
  handshakeProfile,
  progress,
  busy,
  canFlash,
  onWriteModeChange,
  onHandshakeProfileChange,
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
      <label htmlFor="handshake-profile">Handshake Delay Profile</label>
      <select
        id="handshake-profile"
        value={handshakeProfile}
        onChange={(event) => onHandshakeProfileChange(event.currentTarget.value as "normal" | "conservative")}
      >
        <option value="normal">Normal</option>
        <option value="conservative">Conservative</option>
      </select>
      <progress value={progress} max={100} />
      <button disabled={busy || !canFlash} onClick={() => void onFlash()}>
        {busy ? "Working..." : writeMode ? "Flash logo" : "Simulate"}
      </button>
    </section>
  );
}
