// Validation of the appearance attributes and the contrast color (docs/specs/widget.md,
// "Atributos" and "Aparência"). An invalid attribute is ignored, so the panel's value applies.

export const MODES = ["bubble", "inline"] as const;
export const POSITIONS = ["bottom-right", "bottom-left"] as const;
export const THEMES = ["light", "dark", "auto"] as const;
export const STORAGES = ["local", "session", "none"] as const;

const HEX = /^#[0-9a-fA-F]{6}$/;
const WIDGET_KEY = /^kbp_[a-z0-9]{24}$/;

/** Development only: the production bundle has no console (the guard is dropped by the build). */
export function devWarn(message: string): void {
  if (import.meta.env.DEV) console.warn(`[knobridge-chat] ${message}`);
}

/** The attribute value when it is one of `allowed`; otherwise undefined (with a warning). */
export function pick<T extends string>(
  value: string | null | undefined,
  allowed: readonly T[],
  name: string,
): T | undefined {
  if (value === null || value === undefined) return undefined;
  if ((allowed as readonly string[]).includes(value)) return value as T;
  devWarn(`ignoring invalid ${name}="${value}"`);
  return undefined;
}

export function hexColor(value: string | null | undefined): string | undefined {
  if (value === null || value === undefined) return undefined;
  if (HEX.test(value)) return value.toLowerCase();
  devWarn(`ignoring invalid primary-color="${value}"`);
  return undefined;
}

export function isWidgetKey(value: string | null | undefined): value is string {
  return typeof value === "string" && WIDGET_KEY.test(value);
}

/** `api-base` must be an http(s) origin; anything else falls back to the script's origin. */
export function apiOrigin(value: string | null | undefined): string | undefined {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    if (url.protocol === "http:" || url.protocol === "https:") return url.origin;
  } catch {
    // Reported below.
  }
  devWarn(`ignoring invalid api-base="${value}"`);
  return undefined;
}

function luminance(hex: string): number {
  const channel = (offset: number) => {
    const c = Number.parseInt(hex.slice(offset, offset + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(1) + 0.7152 * channel(3) + 0.0722 * channel(5);
}

/** White or black, whichever has the higher WCAG contrast with the primary color. */
export function contrastColor(hex: string): "#ffffff" | "#000000" {
  const l = luminance(hex);
  const withWhite = 1.05 / (l + 0.05);
  const withBlack = (l + 0.05) / 0.05;
  return withWhite >= withBlack ? "#ffffff" : "#000000";
}
