import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { render, renderHook, type RenderResult } from "@testing-library/react";
import type { ReactNode } from "react";
import { createMemoryRouter, type RouteObject } from "react-router";

import { AppProviders, type AppRouter } from "@/app/AppProviders";
import { createQueryClient } from "@/app/queryClient";
import { routes as appRoutes } from "@/app/router";
import { i18n } from "@/i18n";

interface RenderWithProvidersOptions {
  /** Initial URL of the in-memory router. Defaults to "/". */
  path?: string;
  /** Route tree to mount. Defaults to the app routes. */
  routes?: RouteObject[];
  /** "Now" seen by the app (relative dates). Defaults to `TEST_NOW`. */
  now?: Date;
}

/** Fixed "now" of the tests, so relative dates do not depend on the real clock. */
export const TEST_NOW = new Date("2026-10-10T12:00:00Z");

interface RenderWithProvidersResult extends RenderResult {
  /** The in-memory router, to assert on `router.state.location` after redirects. */
  router: AppRouter;
  queryClient: QueryClient;
}

/**
 * The app `QueryClient` without query retries: a failing handler must surface as an error right
 * away instead of after the retry delay, which would make tests slow and timing dependent.
 */
export function createTestQueryClient(): QueryClient {
  const queryClient = createQueryClient();
  const defaults = queryClient.getDefaultOptions();
  queryClient.setDefaultOptions({ ...defaults, queries: { ...defaults.queries, retry: false } });
  return queryClient;
}

/** Renders a route tree with the same providers as the app, using an in-memory router. */
export function renderWithProviders({
  path = "/",
  routes = appRoutes,
  now = TEST_NOW,
}: RenderWithProvidersOptions = {}): RenderWithProvidersResult {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const queryClient = createTestQueryClient();
  const clock = () => new Date(now);

  const result = render(
    <AppProviders router={router} queryClient={queryClient} i18n={i18n} clock={clock} />,
  );
  return { ...result, router, queryClient };
}

/** Renders a TanStack Query hook against a fresh `QueryClient`, returned for cache assertions. */
export function renderQueryHook<Result>(hook: () => Result) {
  const queryClient = createTestQueryClient();
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return { ...renderHook(hook, { wrapper }), queryClient };
}
