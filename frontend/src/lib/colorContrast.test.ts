import { describe, expect, it } from "vitest";

import { contrastRatio, lowContrastThemes, relativeLuminance } from "./colorContrast";

describe("colorContrast", () => {
  it("test_relative_luminance_of_black_and_white", () => {
    expect(relativeLuminance("#000000")).toBe(0);
    expect(relativeLuminance("#ffffff")).toBeCloseTo(1);
  });

  it("test_contrast_ratio_is_symmetric_and_bounded", () => {
    expect(contrastRatio("#000000", "#ffffff")).toBeCloseTo(21);
    expect(contrastRatio("#ffffff", "#000000")).toBeCloseTo(21);
    expect(contrastRatio("#2563eb", "#2563eb")).toBe(1);
  });

  it("test_low_contrast_themes_accepts_the_default_blue_on_light", () => {
    expect(lowContrastThemes("#2563eb", "light")).toEqual([]);
  });

  it("test_low_contrast_themes_flags_yellow_on_light", () => {
    expect(lowContrastThemes("#ffff00", "light")).toEqual(["light"]);
    expect(lowContrastThemes("#ffff00", "auto")).toEqual(["light"]);
  });

  it("test_low_contrast_themes_flags_dark_navy_on_dark", () => {
    expect(lowContrastThemes("#1e293b", "dark")).toEqual(["dark"]);
  });

  it("test_low_contrast_themes_ignores_an_invalid_color", () => {
    expect(lowContrastThemes("blue", "auto")).toEqual([]);
  });
});
