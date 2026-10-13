import { describe, expect, it } from "vitest";

import { defaultMaxLevel, defaultSourceMinLevel, isLevelAbove } from "./responseLevels";

describe("isLevelAbove", () => {
  it.each([
    ["support", "end_user", true],
    ["product_dev", "support", true],
    ["end_user", "end_user", false],
    ["end_user", "product_dev", false],
  ] as const)("test_is_level_above_%s_over_%s_is_%s", (level, other, expected) => {
    expect(isLevelAbove(level, other)).toBe(expected);
  });
});

describe("defaultMaxLevel", () => {
  it.each([
    ["owner", "product_dev"],
    ["admin", "product_dev"],
    ["editor", "end_user"],
    ["viewer", "end_user"],
  ] as const)("test_default_max_level_of_%s_is_%s", (role, expected) => {
    expect(defaultMaxLevel(role)).toBe(expected);
  });
});

describe("defaultSourceMinLevel", () => {
  it.each([
    ["folder", "end_user"],
    ["runner", "end_user"],
    ["tickets", "support"],
    ["cards", "product_dev"],
    ["git", "product_dev"],
  ] as const)("test_default_source_min_level_of_%s_is_%s", (kind, expected) => {
    expect(defaultSourceMinLevel(kind)).toBe(expected);
  });
});
