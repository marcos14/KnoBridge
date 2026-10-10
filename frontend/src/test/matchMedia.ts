/**
 * `window.matchMedia` for jsdom, which has none. Answers the two queries the app asks: the OS dark
 * scheme (theme "system") and the mobile breakpoint (sidebar). Tests flip them with the setters,
 * which notify the registered listeners like a real media query change.
 */
type Listener = (event: MediaQueryListEvent) => void;

const listeners = new Set<Listener>();
let prefersDark = false;
let mobile = false;

function matches(query: string): boolean {
  if (query.includes("prefers-color-scheme: dark")) {
    return prefersDark;
  }
  if (query.includes("max-width")) {
    return mobile;
  }
  return false;
}

function notify(): void {
  for (const listener of listeners) {
    listener({ matches: false } as MediaQueryListEvent);
  }
}

export function installMatchMedia(): void {
  window.matchMedia = (query: string) =>
    ({
      get matches() {
        return matches(query);
      },
      media: query,
      onchange: null,
      addEventListener: (_type: string, listener: Listener) => listeners.add(listener),
      removeEventListener: (_type: string, listener: Listener) => listeners.delete(listener),
      addListener: (listener: Listener) => listeners.add(listener),
      removeListener: (listener: Listener) => listeners.delete(listener),
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList;
}

export function setPrefersDark(value: boolean): void {
  prefersDark = value;
  notify();
}

export function setMobileViewport(value: boolean): void {
  mobile = value;
  notify();
}

export function resetMatchMedia(): void {
  prefersDark = false;
  mobile = false;
  listeners.clear();
}

/** How many media query listeners are registered, to assert subscriptions are released. */
export function matchMediaListenerCount(): number {
  return listeners.size;
}
