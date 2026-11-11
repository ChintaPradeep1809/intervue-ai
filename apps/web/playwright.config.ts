import { defineConfig, devices } from "@playwright/test";

/**
 * Critical-path browser tests. Expects the full local stack to be running
 * (scripts/dev.ps1 or `npm run dev:all`): web on :3000, API on :8100, worker on :8101, seeded DB.
 */
export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 120_000,
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    permissions: ["microphone", "camera"],
    launchOptions: { args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"] },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
