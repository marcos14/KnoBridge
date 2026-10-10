import createClient, { type Middleware } from "openapi-fetch";

import type { paths } from "./schema.gen";

/** Cookie and header of the signed double-submit CSRF check (backend `security/csrf.py`). */
export const CSRF_COOKIE_NAME = "knobridge_csrf";
export const CSRF_HEADER_NAME = "X-CSRF-Token";

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS", "TRACE"]);

/**
 * Requests whose 401 is an expected answer, not an expired session: an anonymous `GET /v1/me`
 * (how the app learns nobody is logged in), a login with wrong credentials, a logout of a
 * session that already ended and an invitation accepted for an address that must log in first
 * (`login_required`, handled by the invitation screen).
 */
const EXPECTED_UNAUTHORIZED = [
  { method: "GET", path: "/v1/me" },
  { method: "POST", path: "/v1/auth/login" },
  { method: "POST", path: "/v1/auth/logout" },
  { method: "POST", path: "/v1/invites/accept" },
];

/**
 * Turns the configured base URL into an absolute one. A relative value such as the default "/"
 * means "same origin as the app" (nginx or the Vite proxy forward /v1 to the API).
 */
export function resolveBaseUrl(configured: string | undefined, origin: string): string {
  const base = configured === undefined || configured === "" ? "/" : configured;
  return new URL(base, origin).href;
}

/** Raised when the API answers with a non-2xx status; `code` comes from the standard error body. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string | undefined;
  readonly details: unknown;

  constructor(status: number, code?: string, details?: unknown) {
    super(`API request failed with status ${String(status)}`);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

/** Whether `error` is an `ApiError` carrying the API error `code`. */
export function isApiErrorCode(error: unknown, code: string): error is ApiError {
  return error instanceof ApiError && error.code === code;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

/** Seconds to wait from a 429 `too_many_attempts` (`details.retry_after_seconds`), if given. */
export function retryAfterSeconds(error: unknown): number | undefined {
  if (!(error instanceof ApiError) || !isRecord(error.details)) {
    return undefined;
  }
  const seconds = error.details.retry_after_seconds;
  return typeof seconds === "number" && seconds > 0 ? seconds : undefined;
}

/** Builds an `ApiError` from a status and a body in the `{"error": {code, message, details}}` shape. */
export function toApiError(status: number, body: unknown): ApiError {
  const error = isRecord(body) ? body.error : undefined;
  if (!isRecord(error) || typeof error.code !== "string") {
    return new ApiError(status);
  }
  return new ApiError(status, error.code, error.details);
}

/** Value of a cookie readable by scripts, or `undefined` when it is not set. */
export function readCookie(name: string, cookies: string = document.cookie): string | undefined {
  for (const part of cookies.split(";")) {
    const [key, ...rest] = part.trim().split("=");
    if (key === name) {
      return decodeURIComponent(rest.join("="));
    }
  }
  return undefined;
}

type UnauthorizedHandler = () => void;

let unauthorizedHandler: UnauthorizedHandler | null = null;

/** Registers who reacts to an expired session (the app shell); `null` unregisters. */
export function setUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
  unauthorizedHandler = handler;
}

function isExpectedUnauthorized(request: Request): boolean {
  const { pathname } = new URL(request.url);
  return EXPECTED_UNAUTHORIZED.some(
    ({ method, path }) => request.method === method && pathname.endsWith(path),
  );
}

/**
 * Echoes the CSRF cookie in the header of unsafe requests and reports unexpected 401s. The cookie
 * is set by login and setup together with the session and expires with it, so a missing cookie
 * means there is no session to protect and the request goes without the header.
 */
export const authMiddleware: Middleware = {
  onRequest({ request }) {
    if (!SAFE_METHODS.has(request.method)) {
      const token = readCookie(CSRF_COOKIE_NAME);
      if (token !== undefined) {
        request.headers.set(CSRF_HEADER_NAME, token);
      }
    }
    return request;
  },
  onResponse({ request, response }) {
    if (response.status === 401 && !isExpectedUnauthorized(request)) {
      unauthorizedHandler?.();
    }
    return response;
  },
};

/** Typed client for the KnoBridge API. Every call to the backend goes through it. */
export function createApiClient(baseUrl: string) {
  const client = createClient<paths>({
    baseUrl,
    // The session lives in an httpOnly cookie; send it even if the API sits on another origin.
    credentials: "include",
    // Resolve fetch on each call instead of capturing it at creation, so interceptors installed
    // later (MSW in tests, instrumentation) see the requests.
    fetch: (request) => globalThis.fetch(request),
  });
  client.use(authMiddleware);
  return client;
}

export const apiClient = createApiClient(
  resolveBaseUrl(import.meta.env.VITE_API_BASE_URL, window.location.origin),
);

interface FetchResult<T> {
  data?: T;
  error?: unknown;
  response: Response;
}

/** Returns the body of a 2xx answer or throws the `ApiError` described by the error body. */
export function unwrap<T>({ data, error, response }: FetchResult<T>): T {
  if (!response.ok) {
    throw toApiError(response.status, error);
  }
  // openapi-fetch fills `data` for every 2xx answer with a body; callers of 204 routes ignore it.
  return data as T;
}
