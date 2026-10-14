// The effective appearance: a valid attribute wins over the panel's configuration
// (docs/specs/widget.md, "Atributos"); CSS variables on the host win over both, in styles.ts.

import type { WidgetMode, WidgetPosition, WidgetPublicConfig, WidgetTheme } from "../api/types.ts";
import { hexColor, MODES, pick, POSITIONS, THEMES } from "../lib/appearance.ts";

export interface AppearanceAttributes {
  mode: string | null;
  position: string | null;
  theme: string | null;
  primaryColor: string | null;
  chatTitle: string | null;
  greeting: string | null;
  placeholder: string | null;
}

export interface View {
  mode: WidgetMode;
  position: WidgetPosition;
  theme: WidgetTheme;
  primary: string;
  title: string;
  greeting: string;
  placeholder: string;
  maxChars: number;
}

// Before the configuration arrives (or when it fails), the panel's defaults.
const DEFAULTS: Omit<WidgetPublicConfig, "public_key" | "product_name" | "level"> = {
  language: "pt-BR",
  title: "",
  greeting: "",
  placeholder: "",
  mode: "bubble",
  position: "bottom-right",
  theme: "auto",
  primary_color: "#2563eb",
  feedback_enabled: false,
  ticket_enabled: false,
  identity_enabled: false,
  question_max_chars: 8000,
};

export function resolveView(
  attributes: AppearanceAttributes,
  config: WidgetPublicConfig | null,
): View {
  const base = config ?? DEFAULTS;
  return {
    mode: pick(attributes.mode, MODES, "mode") ?? base.mode,
    position: pick(attributes.position, POSITIONS, "position") ?? base.position,
    theme: pick(attributes.theme, THEMES, "theme") ?? base.theme,
    primary: hexColor(attributes.primaryColor) ?? base.primary_color,
    title: attributes.chatTitle ?? base.title,
    greeting: attributes.greeting ?? base.greeting,
    placeholder: attributes.placeholder ?? base.placeholder,
    maxChars: base.question_max_chars,
  };
}
