import { describe, expect, it } from "vitest";

import { makeNewRunner, makeRunner } from "@/test/factories";

import { executorState, isHarnessExecutor, ONLINE_WINDOW_MS, runnerStatus } from "./runnerStatus";

const NOW = new Date("2026-10-10T12:00:00Z");

function seenAgo(ms: number): string {
  return new Date(NOW.getTime() - ms).toISOString();
}

describe("runnerStatus", () => {
  it("test_runner_status_online_within_the_window", () => {
    expect(runnerStatus(makeRunner({ last_seen_at: seenAgo(ONLINE_WINDOW_MS) }), NOW)).toBe(
      "online",
    );
  });

  it("test_runner_status_offline_after_the_window", () => {
    const runner = makeRunner({ online: true, last_seen_at: seenAgo(ONLINE_WINDOW_MS + 1) });
    expect(runnerStatus(runner, NOW)).toBe("offline");
  });

  it("test_runner_status_offline_when_never_seen", () => {
    expect(runnerStatus(makeNewRunner(), NOW)).toBe("offline");
  });

  it("test_runner_status_revoked_even_if_seen_recently", () => {
    const runner = makeRunner({ revoked_at: "2026-10-10T11:00:00Z", last_seen_at: seenAgo(0) });
    expect(runnerStatus(runner, NOW)).toBe("revoked");
  });
});

describe("isHarnessExecutor", () => {
  it.each([
    ["claude_code", true],
    ["codex", true],
    ["gemini", false],
  ])("test_is_harness_executor_%s", (name, expected) => {
    expect(isHarnessExecutor(name)).toBe(expected);
  });
});

describe("executorState", () => {
  it.each([
    [{ available: true, authenticated: true }, "ready"],
    [{ available: true, authenticated: null }, "ready"],
    [{ available: true, authenticated: false }, "notAuthenticated"],
    [{ available: false, authenticated: null }, "unavailable"],
  ] as const)("test_executor_state_%#", (flags, expected) => {
    expect(executorState({ name: "codex", version: null, ...flags })).toBe(expected);
  });
});
