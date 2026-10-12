import { defineConfig, devices } from "@playwright/test";

// End-to-end tests against the whole stack of docker-compose.yml + docker-compose.e2e.yml,
// already up (no webServer here): `pnpm e2e:stack`. URLs come from the environment so the stack
// can run on other ports.
const BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost:5173";
const isCI = process.env.CI !== undefined;

export default defineConfig({
  testDir: "./e2e/stack",
  outputDir: "./test-results/stack",
  // The flows share one database and build on each other: one worker, in file order.
  fullyParallel: false,
  workers: 1,
  forbidOnly: isCI,
  // Failures are fixed at the root, never retried away (AGENTS.md, section 5).
  retries: 0,
  timeout: 180_000,
  expect: { timeout: 15_000 },
  reporter: isCI
    ? [["list"], ["html", { open: "never", outputFolder: "playwright-report/stack" }]]
    : "list",
  use: {
    baseURL: BASE_URL,
    locale: "pt-BR",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "stack", use: { ...devices["Desktop Chrome"] } }],
});
