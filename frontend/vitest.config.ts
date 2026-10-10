import { defineConfig, mergeConfig } from "vitest/config";

import viteConfig from "./vite.config.ts";

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: "jsdom",
      setupFiles: ["./src/test/setup.ts"],
      coverage: {
        // Always on, like --cov in the backend: "pnpm test -- --coverage" forwards a literal "--" that
        // vitest ignores, so the gate cannot depend on the flag. test:watch turns it off.
        enabled: true,
        provider: "v8",
        // All source code under src/; the AGENTS.md files there are docs and cannot be parsed as JS.
        include: ["src/**/*.{ts,tsx}"],
        exclude: [
          // DOM bootstrap only: it calls createRoot on the real #root element of index.html, which
          // does not exist under jsdom. Everything it renders (<App />) is covered by App.test.tsx.
          "src/main.tsx",
          "src/**/*.d.ts",
          // Test infrastructure (setup and helpers), not product code.
          "src/test/**",
        ],
        thresholds: {
          lines: 95,
          branches: 95,
          functions: 95,
          statements: 95,
        },
      },
    },
  }),
);
