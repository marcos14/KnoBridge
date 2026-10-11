import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient, unwrap } from "./client";
import { fetchAllPages } from "./pages";
import type { components } from "./schema.gen";

export type Collection = components["schemas"]["CollectionOut"];
export type CollectionInput = components["schemas"]["CollectionCreate"];
export type CollectionChanges = components["schemas"]["CollectionUpdate"];
export type SearchRequest = components["schemas"]["SearchRequest"];
export type SearchResult = components["schemas"]["SearchResult"];

export function collectionsQueryKey(workspaceId: string) {
  return ["api", "workspaces", workspaceId, "collections"] as const;
}

export function collectionQueryKey(workspaceId: string, collectionId: string) {
  return [...collectionsQueryKey(workspaceId), collectionId] as const;
}

/**
 * Every collection of the workspace, ordered by name, with its source, document and chunk counts
 * (any member). A workspace has a handful: the screen pages them locally.
 */
export function useCollections(workspaceId: string) {
  return useQuery({
    queryKey: collectionsQueryKey(workspaceId),
    queryFn: ({ signal }) =>
      fetchAllPages(async (query) =>
        unwrap(
          await apiClient.GET("/v1/workspaces/{workspace_id}/collections", {
            params: { path: { workspace_id: workspaceId }, query },
            signal,
          }),
        ),
      ),
  });
}

/** One collection with its counts; 404 `not_found` when it is not in the workspace. */
export function useCollection(workspaceId: string, collectionId: string) {
  return useQuery({
    queryKey: collectionQueryKey(workspaceId, collectionId),
    queryFn: async ({ signal }) =>
      unwrap(
        await apiClient.GET("/v1/workspaces/{workspace_id}/collections/{collection_id}", {
          params: { path: { workspace_id: workspaceId, collection_id: collectionId } },
          signal,
        }),
      ),
  });
}

/** Reloads the list and every cached collection (the detail shares the key prefix). */
function useRefreshCollections(workspaceId: string) {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: collectionsQueryKey(workspaceId) });
}

/**
 * `POST /v1/workspaces/{id}/collections` (201). 409 `collection_name_taken`; 422
 * `collection_provider_invalid` (credential of another workspace) or
 * `provider_embeddings_unsupported` (Anthropic).
 */
export function useCreateCollection(workspaceId: string) {
  const refresh = useRefreshCollections(workspaceId);
  return useMutation({
    mutationFn: async (body: CollectionInput) =>
      unwrap(
        await apiClient.POST("/v1/workspaces/{workspace_id}/collections", {
          params: { path: { workspace_id: workspaceId } },
          body,
        }),
      ),
    onSuccess: refresh,
  });
}

export interface CollectionUpdate {
  collectionId: string;
  changes: CollectionChanges;
}

/**
 * `PATCH /v1/workspaces/{id}/collections/{collection_id}`: the fields sent change. Provider and
 * model are locked once the collection has documents (409 `collection_embedding_locked`).
 */
export function useUpdateCollection(workspaceId: string) {
  const refresh = useRefreshCollections(workspaceId);
  return useMutation({
    mutationFn: async ({ collectionId, changes }: CollectionUpdate) =>
      unwrap(
        await apiClient.PATCH("/v1/workspaces/{workspace_id}/collections/{collection_id}", {
          params: { path: { workspace_id: workspaceId, collection_id: collectionId } },
          body: changes,
        }),
      ),
    onSuccess: refresh,
  });
}

/** `DELETE /v1/workspaces/{id}/collections/{collection_id}` (204); 409 `collection_in_use`. */
export function useDeleteCollection(workspaceId: string) {
  const refresh = useRefreshCollections(workspaceId);
  return useMutation({
    mutationFn: async (collectionId: string) => {
      unwrap(
        await apiClient.DELETE("/v1/workspaces/{workspace_id}/collections/{collection_id}", {
          params: { path: { workspace_id: workspaceId, collection_id: collectionId } },
        }),
      );
    },
    onSuccess: refresh,
  });
}

/**
 * `POST /v1/workspaces/{id}/collections/{collection_id}/search` (any member): the chunks that best
 * answer the query, best first, with their scores; an empty list when nothing reaches the
 * threshold. Changes nothing, so it refreshes nothing.
 */
export function useSearchCollection(workspaceId: string, collectionId: string) {
  return useMutation({
    mutationFn: async (body: SearchRequest) =>
      unwrap(
        await apiClient.POST("/v1/workspaces/{workspace_id}/collections/{collection_id}/search", {
          params: { path: { workspace_id: workspaceId, collection_id: collectionId } },
          body,
        }),
      ).results,
  });
}
