export function isWebSerialSupported(): boolean {
  return typeof window !== "undefined" && typeof navigator !== "undefined" && Boolean(navigator.serial);
}

export function browserConstraintMessage(): string {
  return "This flasher requires Google Chrome or Chromium with Web Serial on HTTPS (or localhost).";
}
