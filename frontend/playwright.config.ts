import { defineConfig, devices } from "@playwright/test";

// End-to-end tests run against the real stack: the FastAPI backend (seeded with
// `python -m scripts.seed_demo`) on :8000 and the Vite dev server on :5173.
export default defineConfig({
  testDir: "e2e",
  testMatch: "**/*.spec.ts",
  timeout: 60_000,
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  use: {
    baseURL: process.env.OH_BASE_URL ?? "http://localhost:5173",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } }],
});
