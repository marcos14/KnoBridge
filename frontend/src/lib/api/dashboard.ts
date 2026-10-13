import { useQuery } from "@tanstack/react-query";

import { apiClient, unwrap } from "./client";
import type { components } from "./schema.gen";

export type WorkspaceDashboard = components["schemas"]["WorkspaceDashboardOut"];
export type ChecklistItem = components["schemas"]["ChecklistItemOut"];
export type ChecklistKey = ChecklistItem["key"];

export function workspaceDashboardQueryKey(workspaceId: string) {
  return ["api", "workspaces", workspaceId, "dashboard"] as const;
}

/**
 * Cards and first-steps checklist of the workspace home (`GET .../dashboard`, any member).
 * `cost_month` is `null` below admin.
 */
export function useWorkspaceDashboard(workspaceId: string) {
  return useQuery({
    queryKey: workspaceDashboardQueryKey(workspaceId),
    queryFn: async ({ signal }) =>
      unwrap(
        await apiClient.GET("/v1/workspaces/{workspace_id}/dashboard", {
          params: { path: { workspace_id: workspaceId } },
          signal,
        }),
      ),
  });
}
