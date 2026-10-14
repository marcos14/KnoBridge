// Entry point of the bundle (one classic script, IIFE): reads the origin of the <script> that
// loaded it, the default API base, and registers <knobridge-chat> once, so loading the script
// twice on a page does not throw.

import { KnoBridgeChat, setScriptOrigin } from "./element/knobridge-chat.ts";

export const TAG_NAME = "knobridge-chat";

/** The origin of the loading script; null for a module or inline script (no `src`). */
export function originOf(script: Element | null): string | null {
  if (!(script instanceof HTMLScriptElement) || !script.src) return null;
  return new URL(script.src).origin;
}

export function register(registry: CustomElementRegistry = customElements): void {
  if (registry.get(TAG_NAME)) return;
  // document.currentScript is only set while the classic script runs, so it is read right here.
  setScriptOrigin(originOf(document.currentScript));
  registry.define(TAG_NAME, KnoBridgeChat);
}

register();

export { KnoBridgeChat };

declare global {
  interface HTMLElementTagNameMap {
    "knobridge-chat": KnoBridgeChat;
  }
}
