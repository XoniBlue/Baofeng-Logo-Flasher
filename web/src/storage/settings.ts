const KEY_MODEL = "blf.model";
const KEY_WRITE_MODE = "blf.writeMode";

export function loadModel(defaultModel: string): string {
  return localStorage.getItem(KEY_MODEL) ?? defaultModel;
}

export function saveModel(model: string): void {
  localStorage.setItem(KEY_MODEL, model);
}

export function loadWriteMode(): boolean {
  return localStorage.getItem(KEY_WRITE_MODE) === "1";
}

export function saveWriteMode(enabled: boolean): void {
  localStorage.setItem(KEY_WRITE_MODE, enabled ? "1" : "0");
}
