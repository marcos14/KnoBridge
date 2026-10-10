import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { server } from "@/test/server";

import { ApiError, createApiClient, resolveBaseUrl } from "./client";

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
    expect(error.message).toBe("API request failed with status 503");
  });
});

describe("createApiClient", () => {
  it("test_create_api_client_sends_requests_to_base_url", async () => {
    server.use(
      http.get("https://api.example.test/v1/health/live", () =>
        HttpResponse.json({ status: "ok", version: "9.9.9" }),
      ),
    );
    const client = createApiClient("https://api.example.test/");

    const { data } = await client.GET("/v1/health/live");

    expect(data).toEqual({ status: "ok", version: "9.9.9" });
  });
});
