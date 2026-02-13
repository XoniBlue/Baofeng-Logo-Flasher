/**
 * Maps technical error messages to user-friendly explanations.
 * Helps users understand what went wrong and how to fix it.
 */
export function friendlyErrorMessage(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error);

  // Serial port selection errors
  if (message.includes("No port selected") || message.includes("User cancelled")) {
    return "You didn't select a serial port. Click 'Select Serial Port' and choose your radio's USB connection.";
  }

  // Port access errors
  if (message.includes("Failed to open") || message.includes("already open")) {
    return "Couldn't open the serial port. Make sure no other program (like Chirp or PuTTY) is using it, then try again.";
  }

  // Device disconnection
  if (message.includes("device has been lost") || message.includes("disconnected")) {
    return "Radio disconnected. Please reconnect the USB cable securely and try again.";
  }

  // Timeout errors
  if (message.includes("timeout") || message.includes("timed out")) {
    return "Radio didn't respond in time. Make sure it's in programming mode and the cable is properly connected.";
  }

  // Permission errors
  if (message.includes("permission") || message.includes("access denied")) {
    return "Permission denied. On Linux, add your user to the 'dialout' group. On Windows, check device drivers are installed.";
  }

  // File/image errors
  if (message.includes("Failed to load") || message.includes("image")) {
    return "Couldn't process the image. Try a different image file (PNG, JPG, or BMP recommended).";
  }

  // Size mismatch errors
  if (message.includes("size mismatch") || message.includes("Payload size")) {
    return "Image processing failed. The image must be exactly 160x128 pixels or will be auto-resized.";
  }

  // Write confirmation errors
  if (message.includes("WRITE") || message.includes("confirmation")) {
    return "Write confirmation required. You must type 'WRITE' exactly to proceed with flashing.";
  }

  // Network/API errors for counter
  if (message.includes("fetch") || message.includes("network")) {
    return "Network error (flash counter unavailable). You can still flash your radio normally.";
  }

  // Browser compatibility
  if (message.includes("Web Serial") || message.includes("not supported")) {
    return "Your browser doesn't support Web Serial API. Please use Chrome, Edge, Brave, or Opera.";
  }

  // Generic fallback with original message
  return `Error: ${message}`;
}
