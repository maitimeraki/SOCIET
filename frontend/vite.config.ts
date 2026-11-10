/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Dev is same-origin (R5): the SPA and the API share localhost, so the httpOnly `sid`/`csrf`
  // cookies work without cross-site rules. `ws: true` upgrades the /simulate/* WebSockets too.
  server: {
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true, ws: true },
      // `/health` is a top-level backend route (not under `/api`), so it needs its own proxy entry —
      // otherwise the SPA fallback answers it with index.html and HealthDot always reads "offline".
      '/health': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
  // The rest client reads VITE_API_BASE once at import time and fails closed when it is unset, so
  // the suite runs same-origin like dev does through the proxy. Tests that need the unset case
  // stub it away with vi.stubEnv + vi.resetModules.
  test: {
    // Pin TZ so `fmtDate`'s local-time output is deterministic. Verified on this Windows host: Node
    // honours the literal `TZ=UTC` (offset 0, at startup and at runtime) but ignores IANA zone names
    // like `America/New_York` (offset stays −330) — so a named-zone pin would silently do nothing.
    env: { VITE_API_BASE: "", TZ: "UTC" },
  },
  // Split the vendors a route only needs off the entry chunk: the graph stack (Sigma + graphology)
  // and framer-motion are heavy and route-local, and react/router is the stable shared core. The
  // pages themselves split via React.lazy in App.tsx.
  //
  // Vite 8 builds with rolldown, which does not accept Rollup's `output.manualChunks` object map
  // (only a function), so the same three groups are declared with rolldown's `codeSplitting.groups`.
  // `react` is listed first: a group also captures its modules' dependencies, and the graph stack
  // peers on React — claiming React first keeps it out of the sigma chunk.
  build: {
    chunkSizeWarningLimit: 500,
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            { name: "react", test: /node_modules[\\/](react|react-dom|react-router|react-router-dom)[\\/]/ },
            // JS only: main.tsx eagerly imports @react-sigma/core's stylesheet, and a CSS module in
            // this group drags the whole sigma JS chunk into the entry's modulepreload list.
            { name: "sigma", test: /node_modules[\\/](sigma|graphology|graphology-layout-forceatlas2|@react-sigma)[\\/].*\.(?:js|mjs|cjs)$/ },
            { name: "motion", test: /node_modules[\\/]framer-motion[\\/]/ },
          ],
        },
      },
    },
  },
});
