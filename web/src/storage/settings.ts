const KEY_MODEL = "blf.model";
const KEY_WRITE_MODE = "blf.writeMode";

function safeGetItem(key: string): string | null {
  try {
    if (typeof window === "undefined" || !window.localStorage) {
      return null;
    }
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function safeSetItem(key: string, value: string): void {
  try {
    if (typeof window === "undefined" || !window.localStorage) {
      return;
    }
    window.localStorage.setItem(key, value);
  } catch {
    // Ignore persistence failures (private mode, restricted storage, etc).
  }
}

/** Reads persisted model selection or falls back to app default. */
export function loadModel(defaultModel: string): string {
  return safeGetItem(KEY_MODEL) ?? defaultModel;
}

/** Persists selected radio model for next page load. */
export function saveModel(model: string): void {
  safeSetItem(KEY_MODEL, model);
}

/** Reads persisted write mode; false means simulation mode. */
export function loadWriteMode(): boolean {
  return safeGetItem(KEY_WRITE_MODE) === "1";
}

/** Persists write mode toggle as a compact string flag. */
export function saveWriteMode(enabled: boolean): void {
  safeSetItem(KEY_WRITE_MODE, enabled ? "1" : "0");
}
