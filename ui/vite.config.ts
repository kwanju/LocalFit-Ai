/// <reference types="vitest/config" />
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
      "/api": BACKEND,                 // /api/calendar (ADR-020)
      "/admin": BACKEND,               // /admin/reset (테스트용 데이터 초기화)
      "/ws": { target: BACKEND, ws: true },
    },
  },
  // Vitest: UI 로직(ws 생명주기·session reducer·메시지 계약) 자동 검증.
  // UI↔백엔드 경계 버그(세션 종료·채팅 입력 프레임 등)는 Python 테스트로 못 잡혀
  // 사용자가 매번 먼저 발견하던 문제 → 이 계층 테스트로 회귀 방어 (2026-06-08).
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
  },
});
