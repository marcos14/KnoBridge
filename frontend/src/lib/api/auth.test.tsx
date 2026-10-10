import { act, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { makeMe } from "@/test/factories";
import {
  loginInvalidCredentials,
  logoutCsrfFailed,
  logoutUnauthenticated,
  meServerError,
  meUnauthenticated,
} from "@/test/handlers";
import { renderQueryHook } from "@/test/renderWithProviders";
import { server } from "@/test/server";

import { meQueryKey, setupStatusQueryKey, useLogin, useLogout, useMe } from "./auth";
import { ApiError, setUnauthorizedHandler } from "./client";
import { apiHealthQueryKey } from "./health";

afterEach(() => {
  setUnauthorizedHandler(null);
});

describe("useMe", () => {
  it("test_use_me_returns_current_user", async () => {
    const { result } = renderQueryHook(() => useMe());

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data).toEqual(makeMe());
  });

  it("test_use_me_returns_null_without_session", async () => {
    server.use(meUnauthenticated);
    const { result } = renderQueryHook(() => useMe());

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data).toBeNull();
  });

  it("test_use_me_fails_with_api_error_on_server_error", async () => {
    server.use(meServerError);
    const { result } = renderQueryHook(() => useMe());

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(result.current.error).toBeInstanceOf(ApiError);
    expect(result.current.error).toMatchObject({ status: 500, code: "internal_error" });
  });
});

describe("useLogin", () => {
  it("test_use_login_fills_me_cache_with_answer", async () => {
    const { result, queryClient } = renderQueryHook(() => useLogin());

    await act(() => result.current.mutateAsync({ email: "ana@example.test", password: "secret" }));

    expect(queryClient.getQueryData(meQueryKey)).toEqual(makeMe());
  });

  it("test_use_login_fails_with_invalid_credentials_without_session_expiry", async () => {
    const onUnauthorized = vi.fn<() => void>();
    setUnauthorizedHandler(onUnauthorized);
    server.use(loginInvalidCredentials);
    const { result, queryClient } = renderQueryHook(() => useLogin());

    act(() => {
      result.current.mutate({ email: "ana@example.test", password: "wrong" });
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(result.current.error).toMatchObject({ status: 401, code: "invalid_credentials" });
    expect(queryClient.getQueryData(meQueryKey)).toBeUndefined();
    expect(onUnauthorized).not.toHaveBeenCalled();
  });
});

describe("useLogout", () => {
  function seedCache(queryClient: ReturnType<typeof renderQueryHook>["queryClient"]) {
    queryClient.setQueryData(meQueryKey, makeMe());
    queryClient.setQueryData(setupStatusQueryKey, { needs_setup: false });
    queryClient.setQueryData(apiHealthQueryKey, { status: "ok", checks: {} });
    queryClient.setQueryData(["api", "workspaces", "members"], []);
  }

  it("test_use_logout_clears_user_data_and_keeps_anonymous_queries", async () => {
    const { result, queryClient } = renderQueryHook(() => useLogout());
    seedCache(queryClient);

    await act(() => result.current.mutateAsync());

    expect(queryClient.getQueryData(meQueryKey)).toBeNull();
    expect(queryClient.getQueryData(["api", "workspaces", "members"])).toBeUndefined();
    expect(queryClient.getQueryData(setupStatusQueryKey)).toEqual({ needs_setup: false });
    expect(queryClient.getQueryData(apiHealthQueryKey)).toBeDefined();
  });

  it("test_use_logout_treats_ended_session_as_success", async () => {
    server.use(logoutUnauthenticated);
    const { result, queryClient } = renderQueryHook(() => useLogout());
    seedCache(queryClient);

    await act(() => result.current.mutateAsync());

    expect(queryClient.getQueryData(meQueryKey)).toBeNull();
  });

  it("test_use_logout_fails_on_csrf_error_and_keeps_session", async () => {
    server.use(logoutCsrfFailed);
    const { result, queryClient } = renderQueryHook(() => useLogout());
    seedCache(queryClient);

    act(() => {
      result.current.mutate();
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(result.current.error).toMatchObject({ status: 403, code: "csrf_failed" });
    expect(queryClient.getQueryData(meQueryKey)).toEqual(makeMe());
  });
});
