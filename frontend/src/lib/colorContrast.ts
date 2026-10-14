/**
 * WCAG 2.2 contrast of `#RRGGBB` colors, used by the widget screen to warn when the primary color
 * does not reach 3:1 against the widget's background (`docs/specs/widget.md`, "Acessibilidade").
 */

/** `#RRGGBB`, the only form the widget accepts (`^#[0-9a-fA-F]{6}$`). */
export const HEX_COLOR = /^#[0-9a-fA-F]{6}$/;

/** Least contrast of a control against its background (WCAG 1.4.11). */
export const MIN_CONTROL_CONTRAST = 3;

/** Backgrounds of the widget's light and dark themes (`--knobridge-background`). */
export const WIDGET_BACKGROUNDS = { light: "#ffffff", dark: "#111827" } as const;

function channel(value: number): number {
  const srgb = value / 255;
  return srgb <= 0.04045 ? srgb / 12.92 : ((srgb + 0.055) / 1.055) ** 2.4;
}

/** Relative luminance of a `#RRGGBB` color. */
export function relativeLuminance(hex: string): number {
  const value = Number.parseInt(hex.slice(1), 16);
  const red = channel((value >> 16) & 0xff);
  const green = channel((value >> 8) & 0xff);
  const blue = channel(value & 0xff);
  return 0.2126 * red + 0.7152 * green + 0.0722 * blue;
}

/** Contrast ratio between two `#RRGGBB` colors, from 1 to 21. */
export function contrastRatio(first: string, second: string): number {
  const [light, dark] = [relativeLuminance(first), relativeLuminance(second)].sort(
    (a, b) => b - a,
  ) as [number, number];
  return (light + 0.05) / (dark + 0.05);
}

/**
 * The widget themes in which `primary` stays under 3:1 against the background: `auto` checks
 * both. A color that is not `#RRGGBB` yields nothing (the form reports it instead).
 */
export function lowContrastThemes(
  primary: string,
  theme: "light" | "dark" | "auto",
): ("light" | "dark")[] {
  if (!HEX_COLOR.test(primary)) {
    return [];
  }
  const themes = theme === "auto" ? (["light", "dark"] as const) : [theme];
  return themes.filter(
    (item) => contrastRatio(primary, WIDGET_BACKGROUNDS[item]) < MIN_CONTROL_CONTRAST,
  );
}
