import { act } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { makeMe, OTHER_WORKSPACE_ID, WORKSPACE_ID } from "@/test/factories";
import { meWithAccess, workspaceAccessStore } from "@/test/handlers";
import { renderQueryHook } from "@/test/renderWithProviders";
import { server } from "@/test/server";

import { type Me, meQueryKey } from "./auth";
import { useEnterWorkspace, useLeaveWorkspaceAccess } from "./workspaceAccess";

const SUPERADMIN = makeMe({ is_superadmin: true, workspaces: [] });

function seedWorkspaceQuery(
  queryClient: ReturnType<typeof renderQueryHook>["queryClient"],
  workspaceId: string,
) {
  const key = ["api", "workspaces", workspaceId, "members"];
  queryClient.setQueryData(key, []);
  return () => queryClient.getQueryState(key)?.isInvalidated;
}

describe("useEnterWorkspace", () => {
  it("test_enter_workspace_stores_me_and_refreshes_old_and_new_workspace", async () => {
    const store = workspaceAccessStore(SUPERADMIN, { [OTHER_WORKSPACE_ID]: "Beta Help" });
    server.use(...store.handlers);
    const { result, queryClient } = renderQueryHook(() => useEnterWorkspace());
    queryClient.setQueryData<Me>(meQueryKey, meWithAccess(WORKSPACE_ID, "Acme", SUPERADMIN));
    const oldInvalidated = seedWorkspaceQuery(queryClient, WORKSPACE_ID);
    const newInvalidated = seedWorkspaceQuery(queryClient, OTHER_WORKSPACE_ID);

    await act(() => result.current.mutateAsync(OTHER_WORKSPACE_ID));

    expect(store.entered).toEqual([OTHER_WORKSPACE_ID]);
    expect(queryClient.getQueryData<Me>(meQueryKey)?.superadmin_access?.workspace_name).toBe(
      "Beta Help",
    );
    expect(oldInvalidated()).toBe(true);
    expect(newInvalidated()).toBe(true);
  });
});

describe("useLeaveWorkspaceAccess", () => {
  it("test_leave_workspace_access_clears_access_and_refreshes_that_workspace", async () => {
    const store = workspaceAccessStore(SUPERADMIN, { [WORKSPACE_ID]: "Acme" }, WORKSPACE_ID);
    server.use(...store.handlers);
    const { result, queryClient } = renderQueryHook(() => useLeaveWorkspaceAccess());
    queryClient.setQueryData<Me>(meQueryKey, meWithAccess(WORKSPACE_ID, "Acme", SUPERADMIN));
    const invalidated = seedWorkspaceQuery(queryClient, WORKSPACE_ID);
    const otherInvalidated = seedWorkspaceQuery(queryClient, OTHER_WORKSPACE_ID);

    await act(() => result.current.mutateAsync());

    expect(store.left).toBe(1);
    expect(queryClient.getQueryData<Me>(meQueryKey)?.superadmin_access).toBeNull();
    expect(invalidated()).toBe(true);
    expect(otherInvalidated()).toBe(false);
  });

  it("test_leave_workspace_access_without_cached_me_only_stores_answer", async () => {
    server.use(...workspaceAccessStore(SUPERADMIN).handlers);
    const { result, queryClient } = renderQueryHook(() => useLeaveWorkspaceAccess());

    await act(() => result.current.mutateAsync());

    expect(queryClient.getQueryData<Me>(meQueryKey)?.superadmin_access).toBeNull();
  });
});
