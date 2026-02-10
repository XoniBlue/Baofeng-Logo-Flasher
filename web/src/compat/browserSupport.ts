/** Detects whether current browser/runtime exposes Web Serial API. */
export function isWebSerialSupported(): boolean {
  return typeof window !== "undefined" && typeof navigator !== "undefined" && Boolean(navigator.serial);
}

/** User-facing message shown when Web Serial prerequisites are missing. */
export function browserConstraintMessage(): string {
  return "This flasher requires Google Chrome or Chromium with Web Serial on HTTPS (or localhost).";
}
