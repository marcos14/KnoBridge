import { act, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { CURRENT_SESSION_ID, makeMe, makeSession, OTHER_SESSION_ID } from "@/test/factories";
import {
  changePasswordInvalidCurrent,
  meAs,
  resendVerificationAlreadyVerified,
  resendVerificationTooMany,
  revokeSessionCsrfFailed,
  sessionsAs,
  sessionStore,
} from "@/test/handlers";
import { renderQueryHook } from "@/test/renderWithProviders";
import { server } from "@/test/server";

import {
  type Session,
  sessionsQueryKey,
  useChangePassword,
  useResendVerification,
  useRevokeOtherSessions,
  useRevokeSession,
  useSessions,
} from "./account";
import { loggedOutQueryKey, meQueryKey, useMe } from "./auth";

function manySessions(count: number): Session[] {
  return Array.from({ length: count }, (_, index) =>
    makeSession({
      id: `00000000-0000-4000-8000-${String(index).padStart(12, "0")}`,
      current: index === 0,
    }),
  );
}

describe("useSessions", () => {
  it("test_use_sessions_reads_every_page", async () => {
    const offsets: string[] = [];
    const sessions = manySessions(150);
    server.use(
      http.get("*/v1/me/sessions", ({ request }) => {
        offsets.push(new URL(request.url).searchParams.get("offset") ?? "");
        return undefined;
      }),
      sessionsAs(sessions),
    );
    const { result } = renderQueryHook(() => useSessions());

    await waitFor(() => {
      expect(result.current.data).toHaveLength(150);
    });
    expect(offsets).toEqual(["0", "100"]);
  });

  it("test_use_sessions_stops_on_empty_page", async () => {
    server.use(
      http.get("*/v1/me/sessions", () =>
        HttpResponse.json({ items: [], total: 3, limit: 100, offset: 0 }),
      ),
    );
    const { result } = renderQueryHook(() => useSessions());

    await waitFor(() => {
      expect(result.current.data).toEqual([]);
    });
  });
});

describe("useRevokeSession", () => {
  it("test_use_revoke_session_other_refreshes_list", async () => {
    const store = sessionStore();
    server.use(...store.handlers);
    const { result } = renderQueryHook(() => ({
      sessions: useSessions(),
      revoke: useRevokeSession(),
    }));
    await waitFor(() => {
      expect(result.current.sessions.data).toHaveLength(2);
    });

    await act(() => result.current.revoke.mutateAsync({ id: OTHER_SESSION_ID, current: false }));

    await waitFor(() => {
      expect(result.current.sessions.data).toHaveLength(1);
    });
    expect(store.revoked).toEqual([OTHER_SESSION_ID]);
  });

  it("test_use_revoke_session_already_gone_succeeds", async () => {
    server.use(...sessionStore([makeSession()]).handlers);
    const { result } = renderQueryHook(() => useRevokeSession());

    await act(() => result.current.mutateAsync({ id: OTHER_SESSION_ID, current: false }));

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
  });

  it("test_use_revoke_session_current_ends_session_here", async () => {
    const { result, queryClient } = renderQueryHook(() => ({
      me: useMe(),
      revoke: useRevokeSession(),
    }));
    await waitFor(() => {
      expect(result.current.me.data).toEqual(makeMe());
    });

    await act(() => result.current.revoke.mutateAsync({ id: CURRENT_SESSION_ID, current: true }));

    expect(queryClient.getQueryData(meQueryKey)).toBeNull();
    expect(queryClient.getQueryData(loggedOutQueryKey)).toBe(true);
  });

  it("test_use_revoke_session_reports_api_error", async () => {
    server.use(revokeSessionCsrfFailed);
    const { result } = renderQueryHook(() => useRevokeSession());

    act(() => {
      result.current.mutate({ id: OTHER_SESSION_ID, current: false });
    });

    await waitFor(() => {
      expect(result.current.error).toMatchObject({ status: 403, code: "csrf_failed" });
    });
  });
});

describe("useRevokeOtherSessions", () => {
  it("test_use_revoke_other_sessions_keeps_current_one", async () => {
    const third = makeSession({ id: "00000000-0000-4000-8000-0000000000c3", current: false });
    const store = sessionStore([
      makeSession(),
      makeSession({ id: OTHER_SESSION_ID, current: false }),
      third,
    ]);
    server.use(...store.handlers);
    const { result, queryClient } = renderQueryHook(() => useRevokeOtherSessions());

    await act(() => result.current.mutateAsync());

    expect([...store.revoked].sort()).toEqual([OTHER_SESSION_ID, third.id].sort());
    expect(queryClient.getQueryState(sessionsQueryKey)).toBeUndefined();
  });

  it("test_use_revoke_other_sessions_reports_api_error", async () => {
    server.use(revokeSessionCsrfFailed);
    const { result } = renderQueryHook(() => useRevokeOtherSessions());

    act(() => {
      result.current.mutate();
    });

    await waitFor(() => {
      expect(result.current.error).toMatchObject({ status: 403, code: "csrf_failed" });
    });
  });
});

describe("useChangePassword", () => {
  it("test_use_change_password_refreshes_sessions", async () => {
    const { result } = renderQueryHook(() => ({
      sessions: useSessions(),
      change: useChangePassword(),
    }));
    await waitFor(() => {
      expect(result.current.sessions.data).toHaveLength(2);
    });
    server.use(sessionsAs([makeSession()]));

    await act(() =>
      result.current.change.mutateAsync({
        current_password: "senha-atual-qualquer",
        new_password: "uma-frase-longa-e-nova",
      }),
    );

    await waitFor(() => {
      expect(result.current.sessions.data).toHaveLength(1);
    });
  });

  it("test_use_change_password_reports_wrong_current_password", async () => {
    server.use(changePasswordInvalidCurrent);
    const { result } = renderQueryHook(() => useChangePassword());

    act(() => {
      result.current.mutate({ current_password: "errada", new_password: "uma-frase-longa" });
    });

    await waitFor(() => {
      expect(result.current.error).toMatchObject({
        status: 422,
        code: "invalid_current_password",
      });
    });
  });
});

describe("useResendVerification", () => {
  it("test_use_resend_verification_succeeds_with_no_content", async () => {
    const { result } = renderQueryHook(() => useResendVerification());

    await act(() => result.current.mutateAsync());

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
  });

  it("test_use_resend_verification_already_verified_refreshes_me", async () => {
    const unverified = makeMe({ user: { ...makeMe().user, email_verified_at: null } });
    server.use(meAs(unverified), resendVerificationAlreadyVerified);
    const { result } = renderQueryHook(() => ({
      me: useMe(),
      resend: useResendVerification(),
    }));
    await waitFor(() => {
      expect(result.current.me.data).toEqual(unverified);
    });
    server.use(meAs(makeMe()));

    act(() => {
      result.current.resend.mutate();
    });

    await waitFor(() => {
      expect(result.current.me.data).toEqual(makeMe());
    });
    expect(result.current.resend.error).toMatchObject({ code: "email_already_verified" });
  });

  it("test_use_resend_verification_too_many_keeps_me", async () => {
    server.use(resendVerificationTooMany(60));
    const { result, queryClient } = renderQueryHook(() => useResendVerification());

    act(() => {
      result.current.mutate();
    });

    await waitFor(() => {
      expect(result.current.error).toMatchObject({
        status: 429,
        code: "too_many_attempts",
        details: { retry_after_seconds: 60 },
      });
    });
    expect(queryClient.getQueryState(meQueryKey)).toBeUndefined();
  });
});
