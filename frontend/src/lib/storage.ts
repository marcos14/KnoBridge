/**
 * `localStorage` access that never throws. Private windows, blocked site data and sandboxed frames
 * make even reading `window.localStorage` raise; the panel only keeps conveniences there (theme for
 * the first paint, last workspace), so a failure means "nothing stored".
 */
export function readStoredItem(key: string): string | undefined {
  try {
    return window.localStorage.getItem(key) ?? undefined;
  } catch {
    return undefined;
  }
}

/** Saves `value` under `key`; silently does nothing when storage is unavailable. */
export function writeStoredItem(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Storage unavailable: the value is a convenience, losing it is harmless.
  }
}
