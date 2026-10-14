import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";

import { widgetScriptUrl } from "./installSnippets";
import {
  ensureWidgetScript,
  type PreviewAppearance,
  previewAttributes,
  WIDGET_ELEMENT,
} from "./previewElement";

/** Height of the preview area (the widget's inline minimum is 360 px). */
const PREVIEW_HEIGHT = "560px";

/**
 * Live preview (`docs/specs/widget.md`, "Prévia no painel"): the instance's own
 * `/widget/v1/knobridge-chat.js` and a `<knobridge-chat>` in inline mode with the widget's key
 * and the appearance being edited. It talks for real (the instance's origin is always allowed),
 * so the screen says so. The element is built by hand: it is not a React component.
 */
export function WidgetPreview({
  publicKey,
  appearance,
}: {
  publicKey: string;
  appearance: PreviewAppearance;
}) {
  const { t } = useTranslation();
  const hostRef = useRef<HTMLDivElement>(null);
  const elementRef = useRef<HTMLElement>(null);
  // The panel and the instance share the origin: this is where the widget is served.
  const serverUrl = window.location.origin;
  const attributes = JSON.stringify(previewAttributes(serverUrl, appearance));

  useEffect(() => {
    ensureWidgetScript(widgetScriptUrl(serverUrl));
  }, [serverUrl]);

  // A new key is a new widget: a fresh element, so no conversation carries over.
  useEffect(() => {
    const element = document.createElement(WIDGET_ELEMENT);
    element.setAttribute("widget-key", publicKey);
    element.style.display = "block";
    element.style.height = PREVIEW_HEIGHT;
    hostRef.current?.replaceChildren(element);
    elementRef.current = element;
    return () => {
      element.remove();
    };
  }, [publicKey]);

  // The attributes change in place: the element re-renders without losing the conversation.
  useEffect(() => {
    const element = elementRef.current;
    for (const [name, value] of Object.entries(
      JSON.parse(attributes) as Record<string, string | null>,
    )) {
      if (value === null) {
        element?.removeAttribute(name);
      } else {
        element?.setAttribute(name, value);
      }
    }
  }, [attributes, publicKey]);

  return (
    <section aria-labelledby="widget-preview-title" className="flex flex-col gap-3">
      <h2 id="widget-preview-title" className="text-lg font-semibold">
        {t("widgets.preview.title")}
      </h2>
      <p className="text-muted-foreground text-sm">{t("widgets.preview.description")}</p>
      <p role="note" className="rounded-md border border-amber-500/50 px-3 py-2 text-sm">
        {t("widgets.preview.realWarning")}
      </p>
      <div
        ref={hostRef}
        role="region"
        aria-label={t("widgets.preview.areaLabel")}
        className="rounded-md border"
      />
    </section>
  );
}
