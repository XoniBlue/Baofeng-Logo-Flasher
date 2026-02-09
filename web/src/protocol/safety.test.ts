import { describe, expect, it } from "vitest";
import { requireWritePermission, WRITE_CONFIRMATION_TOKEN } from "./safety";

describe("safety policy", () => {
  it("allows simulation without token", () => {
    expect(() =>
      requireWritePermission({
        writeEnabled: false,
        confirmationToken: null,
        interactive: true,
        modelDetected: "UNKNOWN",
        regionKnown: false,
        simulate: true
      })
    ).not.toThrow();
  });

  it("rejects mismatched confirmation token", () => {
    expect(() =>
      requireWritePermission({
        writeEnabled: true,
        confirmationToken: "NOPE",
        interactive: true,
        modelDetected: "UV-5RM",
        regionKnown: true,
        simulate: false
      })
    ).toThrow("token mismatch");
  });

  it("accepts matching confirmation token", () => {
    expect(() =>
      requireWritePermission({
        writeEnabled: true,
        confirmationToken: WRITE_CONFIRMATION_TOKEN,
        interactive: true,
        modelDetected: "UV-17Pro",
        regionKnown: true,
        simulate: false
      })
    ).not.toThrow();
  });
});
