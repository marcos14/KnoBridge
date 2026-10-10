import "@testing-library/jest-dom/vitest";

import { cleanup, configure } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";

import { lazyElementError } from "./elementError";
import { installMatchMedia, resetMatchMedia } from "./matchMedia";
import { server } from "./server";

installMatchMedia();
configure({ getElementError: lazyElementError });

// jsdom parses its default stylesheet on the first getComputedStyle of each document (~70 ms
// alone, several times that in a loaded suite). Paying it here keeps it out of the first test of
// every file, where it used to land inside the first findByRole (its accessibility check).
window.getComputedStyle(document.body);

// Radix popovers (dropdown menu, tooltip) call these browser APIs, which jsdom does not provide.
class ResizeObserverStub {
  observe(): void {
    // Layout does not exist under jsdom: nothing to observe.
  }
  unobserve(): void {
    // See observe().
  }
  disconnect(): void {
    // See observe().
  }
}
globalThis.ResizeObserver = ResizeObserverStub;
Element.prototype.scrollIntoView = () => undefined;
Element.prototype.hasPointerCapture = () => false;
Element.prototype.releasePointerCapture = () => undefined;

// Any request without a handler fails the test: no test talks to a real network.
beforeAll(() => {
  server.listen({ onUnhandledRequest: "error" });
});

afterEach(() => {
  cleanup();
  server.resetHandlers();
  // State the app keeps outside React: stored preferences, the theme class and media queries.
  window.localStorage.clear();
  window.sessionStorage.clear();
  document.documentElement.className = "";
  document.documentElement.removeAttribute("style");
  document.cookie = "sidebar_state=; max-age=0; path=/";
  resetMatchMedia();
});

afterAll(() => {
  server.close();
});
