import { describe, expect, it } from "vitest";

import { cn } from "./utils";

describe("cn", () => {
  it("test_cn_joins_class_names", () => {
    expect(cn("px-2", "font-medium")).toBe("px-2 font-medium");
  });

  it("test_cn_drops_falsy_values", () => {
    expect(cn("px-2", false, undefined, null, "", { hidden: false, block: true })).toBe(
      "px-2 block",
    );
  });

  it("test_cn_lets_the_last_conflicting_tailwind_class_win", () => {
    expect(cn("px-2 py-1", "px-4")).toBe("py-1 px-4");
  });
});
