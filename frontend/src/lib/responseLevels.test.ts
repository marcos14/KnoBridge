import { describe, expect, it } from "vitest";

import { i18n } from "@/i18n";

import {
  defaultMaxLevel,
  defaultSourceMinLevel,
  isLevelAbove,
  levelAudience,
  levelLabel,
  parseLevel,
} from "./responseLevels";

const t = i18n.t;

describe("parseLevel", () => {
  it.each([
    ["end_user", "end_user"],
    ["support", "support"],
    ["product_dev", "product_dev"],
    ["admin", undefined],
    ["", undefined],
    [null, undefined],
    [undefined, undefined],
  ] as const)("test_parse_level_of_%s_is_%s", (value, expected) => {
    expect(parseLevel(value)).toBe(expected);
  });
});

describe("levelLabel", () => {
  it.each([
    ["end_user", "Usuário final"],
    ["support", "Suporte"],
    ["product_dev", "Desenvolvimento e produto"],
  ] as const)("test_level_label_of_%s_is_%s", (level, expected) => {
    expect(levelLabel(level, t)).toBe(expected);
  });

  it("test_level_audience_says_who_the_level_is_for", () => {
    expect(levelAudience("end_user", t)).toMatch(/^Quem usa o sistema/);
  });
});

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
