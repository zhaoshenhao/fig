import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./pages",
  fullyParallel: true,
  retries: 0,
  workers: 1,
  timeout: 30000,
  expect: { timeout: 5000 },
  use: {
    baseURL: "http://localhost:5173",
    headless: true,
    viewport: { width: 1280, height: 800 },
    actionTimeout: 5000,
  },
  webServer: {
    command: "npm run dev",
    port: 5173,
    cwd: "../../src/gui/ui",
    reuseExistingServer: true,
    timeout: 15000,
  },
});
