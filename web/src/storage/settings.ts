const KEY_MODEL = "blf.model";
const KEY_WRITE_MODE = "blf.writeMode";

/** Reads persisted model selection or falls back to app default. */
export function loadModel(defaultModel: string): string {
  return localStorage.getItem(KEY_MODEL) ?? defaultModel;
}

/** Persists selected radio model for next page load. */
export function saveModel(model: string): void {
  localStorage.setItem(KEY_MODEL, model);
}

/** Reads persisted write mode; false means simulation mode. */
export function loadWriteMode(): boolean {
  return localStorage.getItem(KEY_WRITE_MODE) === "1";
}

/** Persists write mode toggle as a compact string flag. */
export function saveWriteMode(enabled: boolean): void {
  localStorage.setItem(KEY_WRITE_MODE, enabled ? "1" : "0");
}
