import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiErrorResponse } from "@/test/handlers";
import { server } from "@/test/server";

import {
  ApiError,
  CSRF_COOKIE_NAME,
  CSRF_HEADER_NAME,
  createApiClient,
  isApiErrorCode,
  readCookie,
  resolveBaseUrl,
  setUnauthorizedHandler,
  toApiError,
  unwrap,
} from "./client";

const BASE = "https://api.example.test/";

function setCsrfCookie(value: string) {
  document.cookie = `${CSRF_COOKIE_NAME}=${value}; path=/`;
}

function clearCsrfCookie() {
  document.cookie = `${CSRF_COOKIE_NAME}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`;
}

describe("resolveBaseUrl", () => {
  it("test_resolve_base_url_defaults_to_app_origin", () => {
    expect(resolveBaseUrl(undefined, "http://app.test")).toBe("http://app.test/");
  });

  it("test_resolve_base_url_treats_empty_value_as_default", () => {
    expect(resolveBaseUrl("", "http://app.test")).toBe("http://app.test/");
  });

  it("test_resolve_base_url_resolves_relative_path_against_origin", () => {
    expect(resolveBaseUrl("/api", "http://app.test")).toBe("http://app.test/api");
  });

  it("test_resolve_base_url_keeps_absolute_url", () => {
    expect(resolveBaseUrl("https://api.example.test", "http://app.test")).toBe(
      "https://api.example.test/",
    );
  });
});

describe("ApiError", () => {
  it("test_api_error_exposes_status", () => {
    const error = new ApiError(503);

    expect(error).toBeInstanceOf(Error);
    expect(error.name).toBe("ApiError");
    expect(error.status).toBe(503);
    expect(error.code).toBeUndefined();
    expect(error.message).toBe("API request failed with status 503");
  });

  it("test_api_error_exposes_code_and_details", () => {
    const error = new ApiError(422, "weak_password", { min_length: 12 });

    expect(error.code).toBe("weak_password");
    expect(error.details).toEqual({ min_length: 12 });
  });
});

describe("isApiErrorCode", () => {
  it("test_is_api_error_code_matches_code_of_api_error", () => {
    expect(isApiErrorCode(new ApiError(400, "invalid_token"), "invalid_token")).toBe(true);
  });

  it("test_is_api_error_code_rejects_other_code_and_other_errors", () => {
    expect(isApiErrorCode(new ApiError(400, "weak_password"), "invalid_token")).toBe(false);
    expect(isApiErrorCode(new TypeError("Failed to fetch"), "invalid_token")).toBe(false);
    expect(isApiErrorCode(null, "invalid_token")).toBe(false);
  });
});

describe("toApiError", () => {
  it("test_to_api_error_reads_standard_error_body", () => {
    const error = toApiError(409, { error: { code: "slug_taken", message: "x", details: null } });

    expect(error).toMatchObject({ status: 409, code: "slug_taken", details: null });
  });

  it("test_to_api_error_without_body_has_no_code", () => {
    expect(toApiError(500, undefined).code).toBeUndefined();
  });

  it("test_to_api_error_ignores_body_in_another_shape", () => {
    expect(toApiError(422, { detail: [] }).code).toBeUndefined();
    expect(toApiError(422, { error: "boom" }).code).toBeUndefined();
    expect(toApiError(422, { error: { code: 42 } }).code).toBeUndefined();
  });
});

describe("readCookie", () => {
  it("test_read_cookie_finds_value_among_others", () => {
    expect(readCookie("b", "a=1; b=two%20words; c=3")).toBe("two words");
  });

  it("test_read_cookie_keeps_equal_signs_in_value", () => {
    expect(readCookie("t", "t=abc==.sig")).toBe("abc==.sig");
  });

  it("test_read_cookie_returns_undefined_when_absent", () => {
    expect(readCookie("missing", "a=1")).toBeUndefined();
    expect(readCookie("missing", "")).toBeUndefined();
  });

  it("test_read_cookie_reads_document_cookie_by_default", () => {
    setCsrfCookie("from-document");

    expect(readCookie(CSRF_COOKIE_NAME)).toBe("from-document");
    clearCsrfCookie();
  });
});

describe("unwrap", () => {
  it("test_unwrap_returns_data_of_ok_response", () => {
    const response = new Response(null, { status: 200 });

    expect(unwrap({ data: { ok: true }, response })).toEqual({ ok: true });
  });

  it("test_unwrap_throws_api_error_with_code", () => {
    const response = new Response(null, { status: 401 });

    expect(() => unwrap({ error: { error: { code: "invalid_credentials" } }, response })).toThrow(
      expect.objectContaining({ status: 401, code: "invalid_credentials" }) as Error,
    );
  });
});

describe("createApiClient", () => {
  afterEach(() => {
    clearCsrfCookie();
    setUnauthorizedHandler(null);
  });

  it("test_create_api_client_sends_requests_to_base_url", async () => {
    server.use(
      http.get("https://api.example.test/v1/health/live", () =>
        HttpResponse.json({ status: "ok", version: "9.9.9" }),
      ),
    );
    const client = createApiClient(BASE);

    const { data } = await client.GET("/v1/health/live");

    expect(data).toEqual({ status: "ok", version: "9.9.9" });
  });

  it("test_create_api_client_includes_credentials", async () => {
    let credentials: RequestCredentials | undefined;
    server.use(
      http.get("*/v1/health/live", ({ request }) => {
        credentials = request.credentials;
        return HttpResponse.json({ status: "ok", version: "1" });
      }),
    );

    await createApiClient(BASE).GET("/v1/health/live");

    expect(credentials).toBe("include");
  });
});

describe("CSRF header", () => {
  let csrfHeader: string | null | undefined;

  beforeEach(() => {
    csrfHeader = undefined;
    server.use(
      http.post("*/v1/auth/logout", ({ request }) => {
        csrfHeader = request.headers.get(CSRF_HEADER_NAME);
        return new HttpResponse(null, { status: 204 });
      }),
      http.get("*/v1/me", ({ request }) => {
        csrfHeader = request.headers.get(CSRF_HEADER_NAME);
        return apiErrorResponse(401, "unauthenticated");
      }),
    );
  });

  afterEach(() => {
    clearCsrfCookie();
  });

  it("test_client_sends_csrf_header_on_post", async () => {
    setCsrfCookie("nonce.signature");

    await createApiClient(BASE).POST("/v1/auth/logout");

    expect(csrfHeader).toBe("nonce.signature");
  });

  it("test_client_does_not_send_csrf_header_on_get", async () => {
    setCsrfCookie("nonce.signature");

    await createApiClient(BASE).GET("/v1/me");

    expect(csrfHeader).toBeNull();
  });

  it("test_client_omits_csrf_header_without_cookie", async () => {
    await createApiClient(BASE).POST("/v1/auth/logout");

    expect(csrfHeader).toBeNull();
  });
});

describe("unauthorized handler", () => {
  const onUnauthorized = vi.fn<() => void>();

  beforeEach(() => {
    onUnauthorized.mockReset();
    setUnauthorizedHandler(onUnauthorized);
    server.use(
      http.get("*/v1/me/sessions", () => apiErrorResponse(401, "unauthenticated")),
      http.get("*/v1/me", () => apiErrorResponse(401, "unauthenticated")),
      http.post("*/v1/auth/login", () => apiErrorResponse(401, "invalid_credentials")),
      http.post("*/v1/auth/logout", () => apiErrorResponse(401, "unauthenticated")),
      http.post("*/v1/invites/accept", () => apiErrorResponse(401, "login_required")),
    );
  });

  afterEach(() => {
    setUnauthorizedHandler(null);
  });

  it("test_client_reports_unexpected_401", async () => {
    await createApiClient(BASE).GET("/v1/me/sessions");

    expect(onUnauthorized).toHaveBeenCalledOnce();
  });

  it("test_client_ignores_expected_401_of_anonymous_me_login_logout_and_invitation", async () => {
    const client = createApiClient(BASE);

    await client.GET("/v1/me");
    await client.POST("/v1/auth/login", { body: { email: "a@example.test", password: "x" } });
    await client.POST("/v1/auth/logout");
    await client.POST("/v1/invites/accept", { body: { token: "synthetic" } });

    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it("test_client_ignores_other_statuses", async () => {
    server.use(http.get("*/v1/me/sessions", () => apiErrorResponse(403, "forbidden")));

    await createApiClient(BASE).GET("/v1/me/sessions");

    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it("test_client_without_handler_ignores_401", async () => {
    setUnauthorizedHandler(null);

    const { response } = await createApiClient(BASE).GET("/v1/me/sessions");

    expect(response.status).toBe(401);
    expect(onUnauthorized).not.toHaveBeenCalled();
  });
});
