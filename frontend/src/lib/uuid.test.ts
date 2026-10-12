import { describe, expect, it } from "vitest";

import { isUuid } from "./uuid";

describe("isUuid", () => {
  it("test_is_uuid_accepts_only_uuids", () => {
    expect(isUuid("00000000-0000-4000-8000-0000000000A1")).toBe(true);
    expect(isUuid("00000000-0000-4000-8000")).toBe(false);
    expect(isUuid("ana")).toBe(false);
    expect(isUuid(null)).toBe(false);
  });
});
