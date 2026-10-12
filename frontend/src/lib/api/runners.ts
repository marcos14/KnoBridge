import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient, unwrap } from "./client";
import { fetchAllPages } from "./pages";
import type { components } from "./schema.gen";

export type Runner = components["schemas"]["RunnerOut"];
export type RunnerCreated = components["schemas"]["RunnerCreated"];
export type RunnerChanges = components["schemas"]["RunnerUpdate"];
export type RunnerExecutor = components["schemas"]["RunnerExecutorOut"];
export type RunnerRepository = components["schemas"]["RunnerRepositoryOut"];
export type HarnessExecutor = components["schemas"]["HarnessExecutor"];

/**
 * How often the runner list asks again, so presence and the last contact stay current: the
 * runner sends a heartbeat every 30 s (`docs/specs/runner.md`).
 */
export const RUNNER_POLL_INTERVAL_MS = 30_000;

export function runnersQueryKey(workspaceId: string) {
  return ["api", "workspaces", workspaceId, "runners"] as const;
}

/**
 * Every runner of the workspace, ordered by name, revoked ones included (owner, admin or editor;
 * never the token). A workspace has a handful: the screens page them locally.
 */
export function useRunners(workspaceId: string, { enabled = true }: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: runnersQueryKey(workspaceId),
    enabled,
    queryFn: ({ signal }) =>
      fetchAllPages(async (query) =>
        unwrap(
          await apiClient.GET("/v1/workspaces/{workspace_id}/runners", {
            params: { path: { workspace_id: workspaceId }, query },
            signal,
          }),
        ),
      ),
    refetchInterval: RUNNER_POLL_INTERVAL_MS,
  });
}

function useRefreshRunners(workspaceId: string) {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: runnersQueryKey(workspaceId) });
}

/**
 * `POST /v1/workspaces/{id}/runners` (201, owner or admin): the runner and its token, the only
 * time the token is ever returned. 409 `runner_name_taken`.
 */
export function useCreateRunner(workspaceId: string) {
  const refresh = useRefreshRunners(workspaceId);
  return useMutation({
    mutationFn: async (name: string) =>
      unwrap(
        await apiClient.POST("/v1/workspaces/{workspace_id}/runners", {
          params: { path: { workspace_id: workspaceId } },
          body: { name },
        }),
      ),
    onSuccess: refresh,
  });
}

export interface RunnerUpdate {
  runnerId: string;
  changes: RunnerChanges;
}

/**
 * `PATCH /v1/workspaces/{id}/runners/{runner_id}`: rename and/or revoke (`revoked: true`,
 * irreversible; the runner's next request gets a 401).
 */
export function useUpdateRunner(workspaceId: string) {
  const refresh = useRefreshRunners(workspaceId);
  return useMutation({
    mutationFn: async ({ runnerId, changes }: RunnerUpdate) =>
      unwrap(
        await apiClient.PATCH("/v1/workspaces/{workspace_id}/runners/{runner_id}", {
          params: { path: { workspace_id: workspaceId, runner_id: runnerId } },
          body: changes,
        }),
      ),
    onSuccess: refresh,
  });
}

/** `DELETE /v1/workspaces/{id}/runners/{runner_id}` (204); 409 `runner_in_use`. */
export function useDeleteRunner(workspaceId: string) {
  const refresh = useRefreshRunners(workspaceId);
  return useMutation({
    mutationFn: async (runnerId: string) => {
      unwrap(
        await apiClient.DELETE("/v1/workspaces/{workspace_id}/runners/{runner_id}", {
          params: { path: { workspace_id: workspaceId, runner_id: runnerId } },
        }),
      );
    },
    onSuccess: refresh,
  });
}
