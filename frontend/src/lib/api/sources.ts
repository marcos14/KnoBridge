import { useQuery } from "@tanstack/react-query";

import { apiClient, unwrap } from "./client";
import { fetchAllPages } from "./pages";
import type { components } from "./schema.gen";

export type Source = components["schemas"]["SourceOut"];
export type SourceKind = components["schemas"]["SourceKind"];
export type RunStatus = components["schemas"]["RunStatus"];

export function sourcesQueryKey(workspaceId: string, collectionId?: string) {
  return ["api", "workspaces", workspaceId, "sources", { collectionId }] as const;
}

/**
 * Every source of the workspace (any member), ordered by name, with its last run; only those of
 * `collectionId` when given (filtered by the API).
 */
export function useSources(workspaceId: string, collectionId?: string) {
  return useQuery({
    queryKey: sourcesQueryKey(workspaceId, collectionId),
    queryFn: ({ signal }) =>
      fetchAllPages(async (page) =>
        unwrap(
          await apiClient.GET("/v1/workspaces/{workspace_id}/sources", {
            params: {
              path: { workspace_id: workspaceId },
              query: { ...page, collection_id: collectionId },
            },
            signal,
          }),
        ),
      ),
  });
}
