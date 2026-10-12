import { describe, expect, it } from "vitest";

import { isHarnessJobActive } from "./harness";

describe("isHarnessJobActive", () => {
  it.each(["queued", "leased", "running", "deferred"] as const)(
    "test_is_harness_job_active_for_%s",
    (status) => {
      expect(isHarnessJobActive(status)).toBe(true);
    },
  );

  it.each(["succeeded", "failed", "cancelled", null, undefined] as const)(
    "test_is_harness_job_not_active_for_%s",
    (status) => {
      expect(isHarnessJobActive(status)).toBe(false);
    },
  );
});
