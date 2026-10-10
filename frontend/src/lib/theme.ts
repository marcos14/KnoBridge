import type { components } from "./api/schema.gen";
import { writeStoredItem } from "./storage";

export type Theme = components["schemas"]["Theme"];
export type ResolvedTheme = "light" | "dark";

/** Key read by the inline script of `index.html` too: keep both in sync. */
export const THEME_STORAGE_KEY = "knobridge-theme";
export const DARK_SCHEME_QUERY = "(prefers-color-scheme: dark)";

/** Every theme, in the order the user menu offers them. */
export const THEMES: readonly Theme[] = ["light", "dark", "system"];

/** Saves the theme for the first paint of the next load (read by the script in `index.html`). */
export function storeTheme(theme: Theme): void {
  writeStoredItem(THEME_STORAGE_KEY, theme);
}

/** "system" follows the operating system preference. */
export function resolveTheme(theme: Theme, prefersDark: boolean): ResolvedTheme {
  if (theme === "system") {
    return prefersDark ? "dark" : "light";
  }
  return theme;
}

export function prefersDarkScheme(): boolean {
  return window.matchMedia(DARK_SCHEME_QUERY).matches;
}

/** Puts the `dark` class (read by the Tailwind `dark` variant) and `color-scheme` on `<html>`. */
export function applyTheme(theme: Theme, root: HTMLElement = document.documentElement): void {
  const resolved = resolveTheme(theme, prefersDarkScheme());
  root.classList.toggle("dark", resolved === "dark");
  root.style.colorScheme = resolved;
}
