import { readFileSync } from "node:fs";
import { join } from "node:path";
import { gzipSync } from "node:zlib";

import { defineConfig, type Plugin } from "vite";

const OUT_DIR = "dist";
const FILE_NAME = "knobridge-chat.js";
// docs/specs/widget.md, "Onde o JS é servido": the single file must stay under 60 KiB gzipped.
const GZIP_BUDGET_BYTES = 60 * 1024;

/** Prints the raw and gzip sizes of the bundle and fails the build above the budget. */
function sizeBudget(): Plugin {
  return {
    name: "knobridge-size-budget",
    apply: "build",
    closeBundle() {
      const code = readFileSync(join(OUT_DIR, FILE_NAME));
      const gzip = gzipSync(code, { level: 9 }).length;
      const kib = (bytes: number) => (bytes / 1024).toFixed(1);
      process.stdout.write(
        `${FILE_NAME}: ${kib(code.length)} KiB raw, ${kib(gzip)} KiB gzip (budget ${kib(GZIP_BUDGET_BYTES)} KiB)\n`,
      );
      if (gzip > GZIP_BUDGET_BYTES) {
        throw new Error(`${FILE_NAME} is ${kib(gzip)} KiB gzipped, above the budget`);
      }
    },
  };
}

export default defineConfig({
  plugins: [sizeBudget()],
  build: {
    outDir: OUT_DIR,
    target: "es2022",
    // One classic script (IIFE) with Lit inside: no dynamic import, no external CSS.
    lib: {
      entry: "src/index.ts",
      formats: ["iife"],
      name: "KnoBridgeChat",
      fileName: () => FILE_NAME,
    },
    sourcemap: false,
  },
});
