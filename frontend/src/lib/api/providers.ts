import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient, unwrap } from "./client";
import { fetchAllPages } from "./pages";
import type { components } from "./schema.gen";

export type Provider = components["schemas"]["ProviderOut"];
export type ProviderKind = components["schemas"]["ProviderKind"];
export type ProviderInput = components["schemas"]["ProviderCreate"];
export type ProviderChanges = components["schemas"]["ProviderUpdate"];
export type ProviderTestResult = components["schemas"]["ProviderTestResult"];

export function providersQueryKey(workspaceId: string) {
  return ["api", "workspaces", workspaceId, "providers"] as const;
}

/**
 * Every LLM provider credential of the workspace, ordered by name (owner, admin or editor; the
 * key comes only masked, in `key_hint`). A workspace has a handful: the screens page them locally.
 */
export function useProviders(workspaceId: string, { enabled = true }: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: providersQueryKey(workspaceId),
    // Off for viewers, whom the API refuses (403): a screen they share with editors skips it.
    enabled,
    queryFn: ({ signal }) =>
      fetchAllPages(async (query) =>
        unwrap(
          await apiClient.GET("/v1/workspaces/{workspace_id}/providers", {
            params: { path: { workspace_id: workspaceId }, query },
            signal,
          }),
        ),
      ),
  });
}

function useRefreshProviders(workspaceId: string) {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: providersQueryKey(workspaceId) });
}

/**
 * `POST /v1/workspaces/{id}/providers` (201): the key is encrypted and never comes back. 409
 * `provider_name_taken`; 422 `provider_kind_not_allowed` for `fake` in production.
 */
export function useCreateProvider(workspaceId: string) {
  const refresh = useRefreshProviders(workspaceId);
  return useMutation({
    mutationFn: async (body: ProviderInput) =>
      unwrap(
        await apiClient.POST("/v1/workspaces/{workspace_id}/providers", {
          params: { path: { workspace_id: workspaceId } },
          body,
        }),
      ),
    onSuccess: refresh,
  });
}

export interface ProviderUpdate {
  providerId: string;
  changes: ProviderChanges;
}

/**
 * `PATCH /v1/workspaces/{id}/providers/{provider_id}`: name, `base_url` (`null` clears it) and,
 * when given, a new key. The kind never changes.
 */
export function useUpdateProvider(workspaceId: string) {
  const refresh = useRefreshProviders(workspaceId);
  return useMutation({
    mutationFn: async ({ providerId, changes }: ProviderUpdate) =>
      unwrap(
        await apiClient.PATCH("/v1/workspaces/{workspace_id}/providers/{provider_id}", {
          params: { path: { workspace_id: workspaceId, provider_id: providerId } },
          body: changes,
        }),
      ),
    onSuccess: refresh,
  });
}

/** `DELETE /v1/workspaces/{id}/providers/{provider_id}` (204); 409 `provider_in_use`. */
export function useDeleteProvider(workspaceId: string) {
  const refresh = useRefreshProviders(workspaceId);
  return useMutation({
    mutationFn: async (providerId: string) => {
      unwrap(
        await apiClient.DELETE("/v1/workspaces/{workspace_id}/providers/{provider_id}", {
          params: { path: { workspace_id: workspaceId, provider_id: providerId } },
        }),
      );
    },
    onSuccess: refresh,
  });
}

/**
 * `POST /v1/workspaces/{id}/providers/{provider_id}/test`: calls the provider with the stored key.
 * A provider failure is still a 200, with `ok: false` and the error `code`.
 */
export function useTestProvider(workspaceId: string) {
  return useMutation({
    mutationFn: async (providerId: string) =>
      unwrap(
        await apiClient.POST("/v1/workspaces/{workspace_id}/providers/{provider_id}/test", {
          params: { path: { workspace_id: workspaceId, provider_id: providerId } },
        }),
      ),
  });
}
