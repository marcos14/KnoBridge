import { describe, expect, it } from "vitest";

import { isRunActive, pollWhile, RUN_POLL_INTERVAL_MS } from "./sources";

describe("isRunActive", () => {
  it.each([
    ["queued", true],
    ["running", true],
    ["succeeded", false],
    ["failed", false],
    ["cancelled", false],
    [undefined, false],
  ] as const)("test_is_run_active_for_%s", (status, expected) => {
    expect(isRunActive(status)).toBe(expected);
  });
});

describe("pollWhile", () => {
  it("test_poll_while_active_uses_the_poll_interval", () => {
    expect(pollWhile(true)).toBe(RUN_POLL_INTERVAL_MS);
  });

  it("test_poll_while_idle_stops_polling", () => {
    expect(pollWhile(false)).toBe(false);
  });
});
