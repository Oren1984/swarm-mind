import { defineConfig, devices } from "@playwright/test";

// The tests run against an already running stack (docker compose up).
export default defineConfig({
  testDir: "e2e",
  testMatch: "*.spec.ts",
  timeout: 180_000,
  workers: 1, // the simulation server is CPU-bound; parallel browsers only add noise
  reporter: [["list"]],
  use: {
    baseURL: process.env.SWARM_URL ?? "http://localhost:8080",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    { name: "mobile", use: { ...devices["Pixel 7"] } },
  ],
});
