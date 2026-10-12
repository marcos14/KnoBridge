import { act, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  makeMe,
  makeWorkspace,
  memberId,
  OTHER_WORKSPACE_ID,
  USER_ID,
  WORKSPACE_ID,
} from "@/test/factories";
import { adminUserStore, adminWorkspaceStore } from "@/test/handlers";
import { renderQueryHook } from "@/test/renderWithProviders";
import { server } from "@/test/server";

import { useAdminUsers, useAdminWorkspaces, useUpdateUser, useUpdateWorkspace } from "./admin";
import { type Me, meQueryKey } from "./auth";

describe("admin listings", () => {
  it("test_use_admin_workspaces_sends_trimmed_search", async () => {
    const store = adminWorkspaceStore();
    server.use(...store.handlers);
    const { result } = renderQueryHook(() =>
      useAdminWorkspaces({ q: "  beta ", limit: 20, offset: 0 }),
    );

    await waitFor(() => {
      expect(result.current.data?.items.map((item) => item.name)).toEqual(["Beta Help"]);
    });
    expect(store.queries[0]?.get("q")).toBe("beta");
  });

  it("test_use_admin_users_omits_blank_search", async () => {
    const store = adminUserStore();
    server.use(...store.handlers);
    const { result } = renderQueryHook(() => useAdminUsers({ q: "   ", limit: 20, offset: 0 }));

    await waitFor(() => {
      expect(result.current.data?.total).toBe(3);
    });
    expect(store.queries[0]?.has("q")).toBe(false);
  });
});

describe("useUpdateWorkspace", () => {
  it("test_update_workspace_refreshes_me_when_superadmin_is_member", async () => {
    server.use(...adminWorkspaceStore().handlers);
    const { result, queryClient } = renderQueryHook(() => useUpdateWorkspace());
    queryClient.setQueryData<Me>(meQueryKey, makeMe());

    await act(() =>
      result.current.mutateAsync({ workspaceId: WORKSPACE_ID, change: { status: "suspended" } }),
    );

    expect(queryClient.getQueryState(meQueryKey)?.isInvalidated).toBe(true);
  });

  it("test_update_workspace_keeps_me_when_superadmin_is_not_member", async () => {
    server.use(...adminWorkspaceStore().handlers);
    const { result, queryClient } = renderQueryHook(() => useUpdateWorkspace());
    queryClient.setQueryData<Me>(meQueryKey, makeMe({ workspaces: [makeWorkspace()] }));

    await act(() =>
      result.current.mutateAsync({ workspaceId: OTHER_WORKSPACE_ID, change: { status: "active" } }),
    );

    expect(queryClient.getQueryState(meQueryKey)?.isInvalidated).toBe(false);
  });

  it("test_update_workspace_without_cached_me_only_refreshes_list", async () => {
    server.use(...adminWorkspaceStore().handlers);
    const { result, queryClient } = renderQueryHook(() => useUpdateWorkspace());

    const updated = await act(() =>
      result.current.mutateAsync({ workspaceId: WORKSPACE_ID, change: { name: "Acme 2" } }),
    );

    expect(updated.name).toBe("Acme 2");
    expect(queryClient.getQueryState(meQueryKey)).toBeUndefined();
  });
});

describe("useUpdateUser", () => {
  it("test_update_user_refreshes_me_when_changing_self", async () => {
    server.use(...adminUserStore().handlers);
    const { result, queryClient } = renderQueryHook(() => useUpdateUser());
    queryClient.setQueryData<Me>(meQueryKey, makeMe({ is_superadmin: true }));

    await act(() =>
      result.current.mutateAsync({ userId: USER_ID, change: { is_superadmin: false } }),
    );

    expect(queryClient.getQueryState(meQueryKey)?.isInvalidated).toBe(true);
  });

  it("test_update_user_keeps_me_when_changing_someone_else", async () => {
    const store = adminUserStore();
    server.use(...store.handlers);
    const { result, queryClient } = renderQueryHook(() => useUpdateUser());
    queryClient.setQueryData<Me>(meQueryKey, makeMe({ is_superadmin: true }));

    await act(() =>
      result.current.mutateAsync({ userId: memberId(1), change: { status: "suspended" } }),
    );

    expect(queryClient.getQueryState(meQueryKey)?.isInvalidated).toBe(false);
    expect(store.changes).toEqual([{ userId: memberId(1), change: { status: "suspended" } }]);
  });
});
