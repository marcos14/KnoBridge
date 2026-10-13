import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient, unwrap } from "./client";
import { fetchAllPages } from "./pages";
import type { components } from "./schema.gen";

export type ApiKey = components["schemas"]["ApiKeyOut"];
export type ApiKeyCreated = components["schemas"]["ApiKeyCreated"];
export type ApiKeyInput = components["schemas"]["ApiKeyCreate"];
export type ApiKeyChanges = components["schemas"]["ApiKeyUpdate"];

export function apiKeysQueryKey(workspaceId: string) {
  return ["api", "workspaces", workspaceId, "api-keys"] as const;
}

/**
 * Every API key of the workspace, ordered by name, revoked ones included (owner or admin; never
 * the key itself). A workspace has a handful: the screen pages them locally.
 */
export function useApiKeys(workspaceId: string) {
  return useQuery({
    queryKey: apiKeysQueryKey(workspaceId),
    queryFn: ({ signal }) =>
      fetchAllPages(async (query) =>
        unwrap(
          await apiClient.GET("/v1/workspaces/{workspace_id}/api-keys", {
            params: { path: { workspace_id: workspaceId }, query },
            signal,
          }),
        ),
      ),
  });
}

function useRefreshApiKeys(workspaceId: string) {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: apiKeysQueryKey(workspaceId) });
}

/**
 * `POST /v1/workspaces/{id}/api-keys` (201): the key and its `kbk_` secret, the only time the
 * secret is ever returned. 409 `api_key_name_taken`; 422 `api_key_product_invalid`.
 */
export function useCreateApiKey(workspaceId: string) {
  const refresh = useRefreshApiKeys(workspaceId);
  return useMutation({
    mutationFn: async (body: ApiKeyInput) =>
      unwrap(
        await apiClient.POST("/v1/workspaces/{workspace_id}/api-keys", {
          params: { path: { workspace_id: workspaceId } },
          body,
        }),
      ),
    onSuccess: refresh,
  });
}

export interface ApiKeyUpdate {
  apiKeyId: string;
  changes: ApiKeyChanges;
}

/**
 * `PATCH /v1/workspaces/{id}/api-keys/{api_key_id}`: name and/or scope (`product_ids: null` is
 * every assistant). 409 `api_key_name_taken` or `api_key_revoked`.
 */
export function useUpdateApiKey(workspaceId: string) {
  const refresh = useRefreshApiKeys(workspaceId);
  return useMutation({
    mutationFn: async ({ apiKeyId, changes }: ApiKeyUpdate) =>
      unwrap(
        await apiClient.PATCH("/v1/workspaces/{workspace_id}/api-keys/{api_key_id}", {
          params: { path: { workspace_id: workspaceId, api_key_id: apiKeyId } },
          body: changes,
        }),
      ),
    onSuccess: refresh,
  });
}

/** `POST /v1/workspaces/{id}/api-keys/{api_key_id}/revoke`: irreversible and idempotent. */
export function useRevokeApiKey(workspaceId: string) {
  const refresh = useRefreshApiKeys(workspaceId);
  return useMutation({
    mutationFn: async (apiKeyId: string) =>
      unwrap(
        await apiClient.POST("/v1/workspaces/{workspace_id}/api-keys/{api_key_id}/revoke", {
          params: { path: { workspace_id: workspaceId, api_key_id: apiKeyId } },
        }),
      ),
    onSuccess: refresh,
  });
}
