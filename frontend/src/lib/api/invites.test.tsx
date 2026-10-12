import { act, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { makeInvitationPreview } from "@/test/factories";
import { acceptInvitationLoginRequired, invitationPreviewInvalidToken } from "@/test/handlers";
import { renderQueryHook } from "@/test/renderWithProviders";
import { server } from "@/test/server";

import { loggedOutQueryKey, meQueryKey } from "./auth";
import { useAcceptInvitation, useInvitationPreview } from "./invites";

describe("useInvitationPreview", () => {
  it("test_use_invitation_preview_loads_invitation", async () => {
    const { result } = renderQueryHook(() => useInvitationPreview("synthetic"));

    await waitFor(() => {
      expect(result.current.data).toEqual(makeInvitationPreview());
    });
  });

  it("test_use_invitation_preview_waits_for_token", () => {
    const { result } = renderQueryHook(() => useInvitationPreview(undefined));

    expect(result.current.fetchStatus).toBe("idle");
    expect(result.current.isPending).toBe(true);
  });

  it("test_use_invitation_preview_reports_invalid_token", async () => {
    server.use(invitationPreviewInvalidToken);
    const { result } = renderQueryHook(() => useInvitationPreview("spent"));

    await waitFor(() => {
      expect(result.current.error).toMatchObject({ status: 400, code: "invalid_token" });
    });
  });
});

describe("useAcceptInvitation", () => {
  it("test_use_accept_invitation_stores_session", async () => {
    const { result, queryClient } = renderQueryHook(() => useAcceptInvitation());
    queryClient.setQueryData(loggedOutQueryKey, true);

    const me = await act(() => result.current.mutateAsync({ token: "synthetic" }));

    expect(me.user.email).toBe("bruno@example.test");
    expect(queryClient.getQueryData(meQueryKey)).toEqual(me);
    expect(queryClient.getQueryData(loggedOutQueryKey)).toBeUndefined();
  });

  it("test_use_accept_invitation_reports_login_required", async () => {
    server.use(acceptInvitationLoginRequired);
    const { result } = renderQueryHook(() => useAcceptInvitation());

    act(() => {
      result.current.mutate({ token: "synthetic" });
    });

    await waitFor(() => {
      expect(result.current.error).toMatchObject({ status: 401, code: "login_required" });
    });
  });
});
