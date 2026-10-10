import { describe, expect, it } from "vitest";

import { setPrefersDark } from "@/test/matchMedia";

import { applyTheme, resolveTheme, storeTheme, THEME_STORAGE_KEY } from "./theme";

describe("theme", () => {
  it("test_store_theme_saves_under_key_read_by_index_html", () => {
    storeTheme("dark");

    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
  });

  it.each([
    ["light", true, "light"],
    ["dark", false, "dark"],
    ["system", true, "dark"],
    ["system", false, "light"],
  ] as const)("test_resolve_theme_%s_with_dark_os_%s_is_%s", (theme, prefersDark, expected) => {
    expect(resolveTheme(theme, prefersDark)).toBe(expected);
  });

  it("test_apply_theme_sets_dark_class_and_color_scheme", () => {
    const root = document.createElement("html");

    applyTheme("dark", root);
    expect(root).toHaveClass("dark");
    expect(root.style.colorScheme).toBe("dark");

    applyTheme("light", root);
    expect(root).not.toHaveClass("dark");
    expect(root.style.colorScheme).toBe("light");
  });

  it("test_apply_theme_system_follows_os_preference", () => {
    setPrefersDark(true);

    applyTheme("system");

    expect(document.documentElement).toHaveClass("dark");
  });
});
