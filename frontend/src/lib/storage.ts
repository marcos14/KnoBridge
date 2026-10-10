type StorageArea = "local" | "session";

function storageFor(area: StorageArea): Storage {
  return area === "local" ? window.localStorage : window.sessionStorage;
}

/**
 * Web storage access that never throws. Private windows, blocked site data and sandboxed frames
 * make even reading `window.localStorage` raise; the panel only keeps conveniences there (theme for
 * the first paint, last workspace, a pending invitation in the tab), so a failure means "nothing
 * stored". `area` picks `localStorage` (default) or `sessionStorage` (this tab only).
 */
export function readStoredItem(key: string, area: StorageArea = "local"): string | undefined {
  try {
    return storageFor(area).getItem(key) ?? undefined;
  } catch {
    return undefined;
  }
}

/** Saves `value` under `key`; silently does nothing when storage is unavailable. */
export function writeStoredItem(key: string, value: string, area: StorageArea = "local"): void {
  try {
    storageFor(area).setItem(key, value);
  } catch {
    // Storage unavailable: the value is a convenience, losing it is harmless.
  }
}

/** Forgets `key`; silently does nothing when storage is unavailable. */
export function removeStoredItem(key: string, area: StorageArea = "local"): void {
  try {
    storageFor(area).removeItem(key);
  } catch {
    // Storage unavailable: there is nothing stored to forget.
  }
}
