import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient, unwrap } from "./client";
import { fetchAllPages } from "./pages";
import type { components } from "./schema.gen";

export type Assistant = components["schemas"]["AssistantOut"];
export type AssistantTone = components["schemas"]["AssistantTone"];
export type AssistantInput = components["schemas"]["AssistantCreate"];
export type AssistantChanges = components["schemas"]["AssistantUpdate"];

export function assistantsQueryKey(workspaceId: string) {
  return ["api", "workspaces", workspaceId, "assistants"] as const;
}

/**
 * Every assistant of the workspace, ordered by name (viewers get only the active ones). A
 * workspace has a handful: the screens page them locally.
 */
export function useAssistants(workspaceId: string) {
  return useQuery({
    queryKey: assistantsQueryKey(workspaceId),
    queryFn: ({ signal }) =>
      fetchAllPages(async (query) =>
        unwrap(
          await apiClient.GET("/v1/workspaces/{workspace_id}/assistants", {
            params: { path: { workspace_id: workspaceId }, query },
            signal,
          }),
        ),
      ),
  });
}

function useRefreshAssistants(workspaceId: string) {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: assistantsQueryKey(workspaceId) });
}

/**
 * `POST /v1/workspaces/{id}/assistants` (201). 409 `assistant_name_taken`; 422
 * `assistant_provider_invalid` when the provider is not a credential of the workspace.
 */
export function useCreateAssistant(workspaceId: string) {
  const refresh = useRefreshAssistants(workspaceId);
  return useMutation({
    mutationFn: async (body: AssistantInput) =>
      unwrap(
        await apiClient.POST("/v1/workspaces/{workspace_id}/assistants", {
          params: { path: { workspace_id: workspaceId } },
          body,
        }),
      ),
    onSuccess: refresh,
  });
}

export interface AssistantUpdate {
  assistantId: string;
  changes: AssistantChanges;
}

/**
 * `PATCH /v1/workspaces/{id}/assistants/{assistant_id}`; an empty `no_source_message` restores
 * the default message.
 */
export function useUpdateAssistant(workspaceId: string) {
  const refresh = useRefreshAssistants(workspaceId);
  return useMutation({
    mutationFn: async ({ assistantId, changes }: AssistantUpdate) =>
      unwrap(
        await apiClient.PATCH("/v1/workspaces/{workspace_id}/assistants/{assistant_id}", {
          params: { path: { workspace_id: workspaceId, assistant_id: assistantId } },
          body: changes,
        }),
      ),
    onSuccess: refresh,
  });
}

/**
 * `DELETE /v1/workspaces/{id}/assistants/{assistant_id}` (204). The assistant's conversations go
 * with it; deactivating keeps them.
 */
export function useDeleteAssistant(workspaceId: string) {
  const refresh = useRefreshAssistants(workspaceId);
  return useMutation({
    mutationFn: async (assistantId: string) => {
      unwrap(
        await apiClient.DELETE("/v1/workspaces/{workspace_id}/assistants/{assistant_id}", {
          params: { path: { workspace_id: workspaceId, assistant_id: assistantId } },
        }),
      );
    },
    onSuccess: refresh,
  });
}
