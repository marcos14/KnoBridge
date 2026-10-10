import { describe, expect, it } from "vitest";

import { initials } from "./initials";

describe("initials", () => {
  it.each([
    ["Ana Maria Lima", "AL"],
    ["ana", "A"],
    ["  bruno   costa ", "BC"],
    ["", ""],
  ])("test_initials_of_%j_is_%j", (name, expected) => {
    expect(initials(name)).toBe(expected);
  });
});
