import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient, unwrap } from "./client";
import { fetchAllPages } from "./pages";
import type { components, operations } from "./schema.gen";

/*
 * Transitional (plan 0009): assistants became products in the API (`/products`, same ids). The
 * screens still speak of assistants until the Products screen replaces them, so this module keeps
 * its names over the product routes and types.
 */
export type Assistant = components["schemas"]["ProductOut"];
export type AssistantTone = components["schemas"]["ProductTone"];
export type AssistantInput = components["schemas"]["ProductCreate"];
export type AssistantChanges = components["schemas"]["ProductUpdate"];
export type TicketWebhookSecret = components["schemas"]["TicketWebhookSecretOut"];
export type TicketWebhookTest = components["schemas"]["TicketWebhookTestOut"];

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
          await apiClient.GET("/v1/workspaces/{workspace_id}/products", {
            params: { path: { workspace_id: workspaceId }, query },
            signal,
          }),
        ),
      ),
  });
}

/** Search, filters, sort and page of `GET /v1/workspaces/{workspace_id}/products` (`docs/specs`, "Listagens"). */
export type AssistantListQuery = NonNullable<
  operations["list_products_v1_workspaces__workspace_id__products_get"]["parameters"]["query"]
>;

/**
 * One page of the assistant list as the screen asks for it (search by name, status, provider, collection, sort). The previous page stays on screen while the next one loads; mutations reload it (same key
 * prefix as the full list).
 */
export function useAssistantPage(workspaceId: string, query: AssistantListQuery) {
  return useQuery({
    queryKey: [...assistantsQueryKey(workspaceId), "page", query],
    queryFn: async ({ signal }) =>
      unwrap(
        await apiClient.GET("/v1/workspaces/{workspace_id}/products", {
          params: { path: { workspace_id: workspaceId }, query },
          signal,
        }),
      ),
    placeholderData: keepPreviousData,
  });
}

function useRefreshAssistants(workspaceId: string) {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: assistantsQueryKey(workspaceId) });
}

/**
 * `POST .../products/{product_id}/duplicate` (201, editor or above): a new assistant with the
 * original's configuration, named "<nome> (cópia)" by the API. The webhook secret is not copied.
 */
export function useDuplicateAssistant(workspaceId: string) {
  const refresh = useRefreshAssistants(workspaceId);
  return useMutation({
    mutationFn: async (assistantId: string) =>
      unwrap(
        await apiClient.POST("/v1/workspaces/{workspace_id}/products/{product_id}/duplicate", {
          params: { path: { workspace_id: workspaceId, product_id: assistantId } },
          body: {},
        }),
      ),
    onSuccess: refresh,
  });
}

/**
 * `POST /v1/workspaces/{id}/products` (201). 409 `product_name_taken` or, while no level of the
 * workspace has a model, `level_not_configured`; 422 `product_name_invalid`.
 */
export function useCreateAssistant(workspaceId: string) {
  const refresh = useRefreshAssistants(workspaceId);
  return useMutation({
    mutationFn: async (body: AssistantInput) =>
      unwrap(
        await apiClient.POST("/v1/workspaces/{workspace_id}/products", {
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
 * `PATCH /v1/workspaces/{id}/products/{product_id}`; an empty `no_source_message` restores
 * the default message.
 */
export function useUpdateAssistant(workspaceId: string) {
  const refresh = useRefreshAssistants(workspaceId);
  return useMutation({
    mutationFn: async ({ assistantId, changes }: AssistantUpdate) =>
      unwrap(
        await apiClient.PATCH("/v1/workspaces/{workspace_id}/products/{product_id}", {
          params: { path: { workspace_id: workspaceId, product_id: assistantId } },
          body: changes,
        }),
      ),
    onSuccess: refresh,
  });
}

/**
 * `POST .../products/{product_id}/ticket-webhook/secret` (201, owner or admin): generates the
 * `kbw_` secret that signs the ticket webhook, replacing the current one at once. The whole secret
 * comes only in this answer; the list is reloaded for `ticket_webhook_configured` and the date.
 */
export function useRotateTicketWebhookSecret(workspaceId: string) {
  const refresh = useRefreshAssistants(workspaceId);
  return useMutation({
    mutationFn: async (assistantId: string) =>
      unwrap(
        await apiClient.POST(
          "/v1/workspaces/{workspace_id}/products/{product_id}/ticket-webhook/secret",
          { params: { path: { workspace_id: workspaceId, product_id: assistantId } } },
        ),
      ),
    onSuccess: refresh,
  });
}

/**
 * `POST .../products/{product_id}/ticket-webhook/test` (editor or above): one signed
 * `ticket.test` event to the saved URL, without retries. 200 also when the destination fails
 * (`ok: false` with `error`); 409 `ticket_webhook_not_configured` without URL or secret.
 */
export function useTestTicketWebhook(workspaceId: string) {
  return useMutation({
    mutationFn: async (assistantId: string) =>
      unwrap(
        await apiClient.POST(
          "/v1/workspaces/{workspace_id}/products/{product_id}/ticket-webhook/test",
          { params: { path: { workspace_id: workspaceId, product_id: assistantId } } },
        ),
      ),
  });
}

/**
 * `DELETE /v1/workspaces/{id}/products/{product_id}` (204). The assistant's conversations go
 * with it; deactivating keeps them.
 */
export function useDeleteAssistant(workspaceId: string) {
  const refresh = useRefreshAssistants(workspaceId);
  return useMutation({
    mutationFn: async (assistantId: string) => {
      unwrap(
        await apiClient.DELETE("/v1/workspaces/{workspace_id}/products/{product_id}", {
          params: { path: { workspace_id: workspaceId, product_id: assistantId } },
        }),
      );
    },
    onSuccess: refresh,
  });
}
