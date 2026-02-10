import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

/** Vite build/test config for the Web Serial flasher frontend. */
export default defineConfig({
  // React transform and Fast Refresh support.
  plugins: [react()],
  // Relative asset paths keep static hosting/deployment simple.
  base: "./",
  test: {
    // Component/unit tests run in a browser-like DOM runtime.
    environment: "jsdom",
    include: ["src/**/*.test.ts"]
  }
});
