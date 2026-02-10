export const WRITE_CONFIRMATION_TOKEN = "WRITE";

/** Inputs required to validate potentially destructive flash operations. */
export interface SafetyContextLike {
  writeEnabled: boolean;
  confirmationToken?: string | null;
  interactive: boolean;
  modelDetected: string;
  regionKnown: boolean;
  simulate: boolean;
}

/** Enforces UI safety checks before any write-mode operation is allowed. */
export function requireWritePermission(ctx: SafetyContextLike): void {
  if (ctx.simulate) {
    return;
  }
  if (!ctx.writeEnabled) {
    throw new Error("Write mode is disabled.");
  }
  if (!ctx.modelDetected || ctx.modelDetected === "UNKNOWN") {
    throw new Error("Unknown model. Refusing write.");
  }
  if (!ctx.regionKnown) {
    throw new Error("Unknown target region. Refusing write.");
  }
  const provided = (ctx.confirmationToken ?? "").trim().toUpperCase();
  if (provided !== WRITE_CONFIRMATION_TOKEN) {
    throw new Error("Write confirmation token mismatch.");
  }
}
