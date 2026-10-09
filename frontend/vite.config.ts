import { defineConfig } from "vitest/config";

// In development the dashboard proxies /api to the local FastAPI server.
export default defineConfig({
  server: {
    port: 5173,
    proxy: { "/api": process.env.SWARM_API_URL ?? "http://127.0.0.1:8000" },
  },
  test: { include: ["tests/**/*.test.ts"] },
});
