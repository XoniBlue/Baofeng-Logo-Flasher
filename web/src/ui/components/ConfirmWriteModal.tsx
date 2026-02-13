import { useState } from "react";

interface ConfirmWriteModalProps {
  model: string;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * Professional modal dialog for confirming destructive radio write operations.
 * Requires typing "WRITE" to enable confirmation button as safety mechanism.
 */
export function ConfirmWriteModal({ model, onConfirm, onCancel }: ConfirmWriteModalProps): JSX.Element {
  const [input, setInput] = useState("");
  const isValid = input.trim().toUpperCase() === "WRITE";

  const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>): void => {
    if (event.key === "Enter" && isValid) {
      onConfirm();
    } else if (event.key === "Escape") {
      onCancel();
    }
  };

  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <h2>⚠️ Confirm Radio Write</h2>
        <p>
          You are about to flash: <strong>{model}</strong>
        </p>
        <p>This operation will modify your radio's boot logo.</p>
        <p className="modal-instruction">
          Type <code>WRITE</code> to confirm:
        </p>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="WRITE"
          autoFocus
          className="modal-input"
        />
        <div className="modal-actions">
          <button onClick={onCancel} className="button-secondary">
            Cancel
          </button>
          <button onClick={onConfirm} disabled={!isValid} className="button-danger">
            Confirm Flash
          </button>
        </div>
      </div>
    </div>
  );
}
