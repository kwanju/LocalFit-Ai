import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";

// Dev proxy keeps the SPA same-origin with the FastAPI backend (127.0.0.1:8000,
// ADR-002 local-only). REST + WebSocket are proxied so the client uses relative
// paths and never needs CORS. In prod the built assets are served by the backend.
const BACKEND = "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/health": BACKEND,
      "/sessions": BACKEND,
      "/routines": BACKEND,
      "/onboarding": BACKEND,
      "/ws": { target: BACKEND, ws: true },
    },
  },
});
