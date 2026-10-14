/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // The rest client reads VITE_API_BASE once at import time and fails closed when it is unset, so
  // the suite runs same-origin like dev does through the proxy. Tests that need the unset case
  // stub it away with vi.stubEnv + vi.resetModules.
  test: {
    env: { VITE_API_BASE: "" },
  },
});
