import { type QueryClient, useMutation, useQueryClient } from "@tanstack/react-query";

import { type Me, meQueryKey } from "./auth";
import { apiClient, unwrap } from "./client";

/** Workspace of the superadmin access active in the cached `me`, if any. */
function accessedWorkspaceIds(queryClient: QueryClient): string[] {
  const workspaceId = queryClient.getQueryData<Me | null>(meQueryKey)?.superadmin_access
    ?.workspace_id;
  return workspaceId === undefined ? [] : [workspaceId];
}

/**
 * Takes the `me` that came back and invalidates the cached data of the workspaces whose access
 * changed: the effective role there is not the same, so lists and permissions must be read again.
 * Not awaited, so the screen can navigate away before a refetch it no longer needs.
 */
function storeAccessChange(queryClient: QueryClient, me: Me, workspaceIds: readonly string[]) {
  queryClient.setQueryData(meQueryKey, me);
  for (const workspaceId of new Set(workspaceIds)) {
    void queryClient.invalidateQueries({ queryKey: ["api", "workspaces", workspaceId] });
  }
}

/**
 * `POST /v1/admin/workspaces/{id}/enter`: the superadmin enters the workspace with the effective
 * admin role, in this session only (404 `not_found`, 403 `workspace_suspended`). Entering another
 * one replaces the previous access.
 */
export function useEnterWorkspace() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (workspaceId: string) =>
      unwrap(
        await apiClient.POST("/v1/admin/workspaces/{workspace_id}/enter", {
          params: { path: { workspace_id: workspaceId } },
        }),
      ),
    onMutate: () => accessedWorkspaceIds(queryClient),
    onSuccess: (me, workspaceId, previous) => {
      storeAccessChange(queryClient, me, [...previous, workspaceId]);
    },
  });
}

/** `DELETE /v1/admin/workspace-access`: ends the superadmin access of this session. */
export function useLeaveWorkspaceAccess() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => unwrap(await apiClient.DELETE("/v1/admin/workspace-access")),
    onMutate: () => accessedWorkspaceIds(queryClient),
    onSuccess: (me, _variables, previous) => {
      storeAccessChange(queryClient, me, previous);
    },
  });
}
