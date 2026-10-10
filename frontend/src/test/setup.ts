import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";

import { installMatchMedia, resetMatchMedia } from "./matchMedia";
import { server } from "./server";

installMatchMedia();

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
