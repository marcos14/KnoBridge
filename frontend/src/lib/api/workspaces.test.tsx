import { act } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { makeMe, makeWorkspace, OTHER_WORKSPACE_ID, WORKSPACE_ID } from "@/test/factories";
import { renderQueryHook } from "@/test/renderWithProviders";

import { type Me, meQueryKey } from "./auth";
import { useRenameWorkspace } from "./workspaces";

describe("useRenameWorkspace", () => {
  it("test_rename_workspace_updates_only_that_workspace_in_me", async () => {
    const other = makeWorkspace({ id: OTHER_WORKSPACE_ID, name: "Outro" });
    const { result, queryClient } = renderQueryHook(() => useRenameWorkspace(WORKSPACE_ID));
    queryClient.setQueryData<Me>(meQueryKey, makeMe({ workspaces: [makeWorkspace(), other] }));

    await act(() => result.current.mutateAsync("Novo nome"));

    const me = queryClient.getQueryData<Me>(meQueryKey);
    expect(me?.workspaces.map((workspace) => workspace.name)).toEqual(["Novo nome", "Outro"]);
  });

  it("test_rename_workspace_without_cached_me_keeps_cache_empty", async () => {
    const { result, queryClient } = renderQueryHook(() => useRenameWorkspace(WORKSPACE_ID));

    const workspace = await act(() => result.current.mutateAsync("Novo nome"));

    expect(workspace.name).toBe("Novo nome");
    expect(queryClient.getQueryData(meQueryKey)).toBeUndefined();
  });
});
