import { useSyncExternalStore } from "react";

const MOBILE_BREAKPOINT = 768;
const MOBILE_QUERY = `(max-width: ${String(MOBILE_BREAKPOINT - 1)}px)`;

function subscribe(onChange: () => void): () => void {
  const mql = window.matchMedia(MOBILE_QUERY);
  mql.addEventListener("change", onChange);
  return () => {
    mql.removeEventListener("change", onChange);
  };
}

function getSnapshot(): boolean {
  return window.matchMedia(MOBILE_QUERY).matches;
}

/**
 * Whether the viewport is narrower than the mobile breakpoint. Rewritten from the shadcn version
 * with `useSyncExternalStore`, which the strict React hooks lint accepts (no setState in effect).
 */
export function useIsMobile(): boolean {
  return useSyncExternalStore(subscribe, getSnapshot);
}
