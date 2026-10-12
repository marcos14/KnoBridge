import { useMutation, useQueryClient } from "@tanstack/react-query";

import { type Me, meQueryKey } from "./auth";
import { apiClient, unwrap } from "./client";
import type { components } from "./schema.gen";

export type Workspace = components["schemas"]["WorkspaceOut"];

/** Copy of `me` with the name of workspace `workspace.id` replaced. */
function withWorkspaceName(me: Me, workspace: Workspace): Me {
  return {
    ...me,
    workspaces: me.workspaces.map((item) =>
      item.id === workspace.id ? { ...item, name: workspace.name } : item,
    ),
  };
}

/**
 * `PATCH /v1/workspaces/{id}` (owner or admin): renames the workspace; the slug stays. The new
 * name goes into the `useMe` cache, which the workspace switcher reads.
 */
export function useRenameWorkspace(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (name: string) =>
      unwrap(
        await apiClient.PATCH("/v1/workspaces/{workspace_id}", {
          params: { path: { workspace_id: workspaceId } },
          body: { name },
        }),
      ),
    onSuccess: (workspace) => {
      const me = queryClient.getQueryData<Me | null>(meQueryKey);
      if (me) {
        queryClient.setQueryData<Me>(meQueryKey, withWorkspaceName(me, workspace));
      }
    },
  });
}
