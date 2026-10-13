import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient, unwrap } from "./client";
import { workspaceDashboardQueryKey } from "./dashboard";
import type { components } from "./schema.gen";

export type ResponseLevel = components["schemas"]["ResponseLevel"];
export type WorkspaceLevel = components["schemas"]["WorkspaceLevelOut"];
export type WorkspaceLevelChanges = components["schemas"]["WorkspaceLevelUpdate"];

/** The three response levels, from the least to the most technical (`docs/specs/produtos-e-niveis.md`). */
export const RESPONSE_LEVELS: readonly ResponseLevel[] = ["end_user", "support", "product_dev"];

export function workspaceLevelsQueryKey(workspaceId: string) {
  return ["api", "workspaces", workspaceId, "levels"] as const;
}

/**
 * `GET /v1/workspaces/{id}/levels` (owner or admin): the three levels in order, each with its
 * credential, model, temperature, effective instructions, the default text and the estimated cost.
 */
export function useWorkspaceLevels(workspaceId: string) {
  return useQuery({
    queryKey: workspaceLevelsQueryKey(workspaceId),
    queryFn: async ({ signal }) =>
      unwrap(
        await apiClient.GET("/v1/workspaces/{workspace_id}/levels", {
          params: { path: { workspace_id: workspaceId } },
          signal,
        }),
      ).items,
  });
}

export interface WorkspaceLevelUpdate {
  level: ResponseLevel;
  changes: WorkspaceLevelChanges;
}

/**
 * `PATCH /v1/workspaces/{id}/levels/{level}` (owner or admin): omitted fields stay,
 * `instructions: null` restores the default text and `provider_id` with `model` null turn the
 * level off. The saved level replaces its row in the cache; the home checklist is reloaded,
 * since one of its steps is configuring the `end_user` level.
 */
export function useUpdateWorkspaceLevel(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ level, changes }: WorkspaceLevelUpdate) =>
      unwrap(
        await apiClient.PATCH("/v1/workspaces/{workspace_id}/levels/{level}", {
          params: { path: { workspace_id: workspaceId, level } },
          body: changes,
        }),
      ),
    onSuccess: (saved) => {
      queryClient.setQueryData<WorkspaceLevel[]>(workspaceLevelsQueryKey(workspaceId), (levels) =>
        levels?.map((item) => (item.level === saved.level ? saved : item)),
      );
      void queryClient.invalidateQueries({ queryKey: workspaceDashboardQueryKey(workspaceId) });
    },
  });
}
