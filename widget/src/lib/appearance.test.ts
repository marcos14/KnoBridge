import { afterEach, describe, expect, it, vi } from "vitest";

import {
  apiOrigin,
  contrastColor,
  devWarn,
  hexColor,
  isWidgetKey,
  MODES,
  pick,
} from "./appearance.ts";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
});

describe("appearance", () => {
  it("test_pick_returns_allowed_values_and_warns_on_invalid", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);

    expect(pick("inline", MODES, "mode")).toBe("inline");
    expect(pick(null, MODES, "mode")).toBeUndefined();
    expect(pick(undefined, MODES, "mode")).toBeUndefined();
    expect(pick("modal", MODES, "mode")).toBeUndefined();
    expect(warn).toHaveBeenCalledWith('[knobridge-chat] ignoring invalid mode="modal"');
  });

  it("test_dev_warn_is_silent_in_production", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    vi.stubEnv("DEV", false);

    devWarn("x");

    expect(warn).not.toHaveBeenCalled();
  });

  it("test_hex_color_validates_and_lowercases", () => {
    vi.spyOn(console, "warn").mockImplementation(() => undefined);

    expect(hexColor("#AABBCC")).toBe("#aabbcc");
    expect(hexColor("red")).toBeUndefined();
    expect(hexColor(null)).toBeUndefined();
    expect(hexColor(undefined)).toBeUndefined();
  });

  it("test_is_widget_key_follows_the_kbp_format", () => {
    expect(isWidgetKey("kbp_3k9x2m4q7w8e1r5t6y0u2i4o")).toBe(true);
    expect(isWidgetKey("kbp_short")).toBe(false);
    expect(isWidgetKey(null)).toBe(false);
  });

  it("test_api_origin_keeps_only_http_origins", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);

    expect(apiOrigin("https://kb.example.com/ignored/path")).toBe("https://kb.example.com");
    expect(apiOrigin(null)).toBeUndefined();
    expect(apiOrigin("")).toBeUndefined();
    expect(apiOrigin("ftp://kb.example.com")).toBeUndefined();
    expect(apiOrigin("not a url")).toBeUndefined();
    expect(warn).toHaveBeenCalledTimes(2);
  });

  it("test_contrast_color_picks_the_more_readable_text", () => {
    expect(contrastColor("#2563eb")).toBe("#ffffff");
    expect(contrastColor("#000000")).toBe("#ffffff");
    expect(contrastColor("#fde047")).toBe("#000000");
    expect(contrastColor("#ffffff")).toBe("#000000");
  });
});
