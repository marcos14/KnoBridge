import { act, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { makeMe } from "@/test/factories";
import { meAs, resetPasswordInvalidToken } from "@/test/handlers";
import { renderQueryHook } from "@/test/renderWithProviders";
import { server } from "@/test/server";

import { meQueryKey, useMe } from "./auth";
import { useForgotPassword, useResetPassword, useVerifyEmail } from "./recovery";

describe("useForgotPassword", () => {
  it("test_use_forgot_password_succeeds_with_no_content", async () => {
    const { result } = renderQueryHook(() => useForgotPassword());

    await act(() => result.current.mutateAsync({ email: "ana@example.test" }));

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
  });
});

describe("useResetPassword", () => {
  it("test_use_reset_password_succeeds_with_no_content", async () => {
    const { result } = renderQueryHook(() => useResetPassword());

    await act(() => result.current.mutateAsync({ token: "t", password: "uma-frase-longa" }));

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
  });

  it("test_use_reset_password_reports_invalid_token", async () => {
    server.use(resetPasswordInvalidToken);
    const { result } = renderQueryHook(() => useResetPassword());

    act(() => {
      result.current.mutate({ token: "spent", password: "uma-frase-longa" });
    });

    await waitFor(() => {
      expect(result.current.error).toMatchObject({ status: 400, code: "invalid_token" });
    });
  });
});

describe("useVerifyEmail", () => {
  it("test_use_verify_email_refreshes_me", async () => {
    const unverified = makeMe({ user: { ...makeMe().user, email_verified_at: null } });
    server.use(meAs(unverified));
    const { result, queryClient } = renderQueryHook(() => ({
      me: useMe(),
      verify: useVerifyEmail(),
    }));
    await waitFor(() => {
      expect(result.current.me.data).toEqual(unverified);
    });
    server.use(meAs(makeMe()));

    await act(() => result.current.verify.mutateAsync({ token: "t" }));

    expect(queryClient.getQueryData(meQueryKey)).toEqual(makeMe());
  });
});
