import createClient from "openapi-fetch";

import type { paths } from "./schema.gen";

/**
 * Turns the configured base URL into an absolute one. A relative value such as the default "/"
 * means "same origin as the app" (nginx or the Vite proxy forward /v1 to the API).
 */
export function resolveBaseUrl(configured: string | undefined, origin: string): string {
  const base = configured === undefined || configured === "" ? "/" : configured;
  return new URL(base, origin).href;
}

/** Raised when the API answers with a non-2xx status. */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number) {
    super(`API request failed with status ${String(status)}`);
    this.name = "ApiError";
    this.status = status;
  }
}

/** Typed client for the KnoBridge API. Every call to the backend goes through it. */
export function createApiClient(baseUrl: string) {
  return createClient<paths>({
    baseUrl,
    // Resolve fetch on each call instead of capturing it at creation, so interceptors installed
    // later (MSW in tests, instrumentation) see the requests.
    fetch: (request) => globalThis.fetch(request),
  });
}

export const apiClient = createApiClient(
  resolveBaseUrl(import.meta.env.VITE_API_BASE_URL, window.location.origin),
);
