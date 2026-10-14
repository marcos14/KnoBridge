import type { WidgetTheme } from "@/lib/api/widgets";
import { HEX_COLOR } from "@/lib/colorContrast";

/** Id of the `<script>` the preview adds to the page, once per page load. */
export const WIDGET_SCRIPT_ID = "knobridge-widget-script";

/** Tag of the widget's custom element. */
export const WIDGET_ELEMENT = "knobridge-chat";

/** The appearance being edited, not saved yet: it goes to the element as attributes. */
export interface PreviewAppearance {
  theme: WidgetTheme;
  primaryColor: string;
  title: string;
  greeting: string;
  placeholder: string;
}

/**
 * Adds the instance's widget script to the page unless it is there already (the script defines
 * the element only once anyway, but loading it again would be a wasted request).
 */
export function ensureWidgetScript(src: string): void {
  if (document.getElementById(WIDGET_SCRIPT_ID) !== null) {
    return;
  }
  const script = document.createElement("script");
  script.id = WIDGET_SCRIPT_ID;
  script.src = src;
  document.head.append(script);
}

/**
 * The element's attributes for the appearance (`null` removes one): inline, nothing kept in the
 * browser, and the values being edited; an invalid color or an empty title or placeholder falls
 * back to the saved configuration, while an empty greeting means "no greeting", as on save.
 */
export function previewAttributes(
  serverUrl: string,
  appearance: PreviewAppearance,
): Record<string, string | null> {
  const color = appearance.primaryColor.trim();
  const title = appearance.title.trim();
  return {
    "api-base": serverUrl,
    mode: "inline",
    storage: "none",
    theme: appearance.theme,
    "primary-color": HEX_COLOR.test(color) ? color.toLowerCase() : null,
    title: title === "" ? null : title,
    greeting: appearance.greeting,
    placeholder: appearance.placeholder.trim() === "" ? null : appearance.placeholder,
  };
}
