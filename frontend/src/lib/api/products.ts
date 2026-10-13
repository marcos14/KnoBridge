import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient, unwrap } from "./client";
import { fetchAllPages } from "./pages";
import type { components, operations } from "./schema.gen";

/*
 * Products (plan 0009, `docs/specs/produtos-e-niveis.md`): the systems people ask about, which
 * replaced the assistants with the same ids. The model, credential and temperature are the
 * workspace levels' (`levels.ts`), not the product's.
 */
export type Product = components["schemas"]["ProductOut"];
export type ProductTone = components["schemas"]["ProductTone"];
export type ProductInput = components["schemas"]["ProductCreate"];
export type ProductChanges = components["schemas"]["ProductUpdate"];
export type TicketWebhookSecret = components["schemas"]["TicketWebhookSecretOut"];
export type TicketWebhookTest = components["schemas"]["TicketWebhookTestOut"];

export function productsQueryKey(workspaceId: string) {
  return ["api", "workspaces", workspaceId, "products"] as const;
}

/**
 * Every product of the workspace, ordered by name (viewers get only the active ones). A
 * workspace has a handful: the screens page them locally.
 */
export function useProducts(workspaceId: string) {
  return useQuery({
    queryKey: productsQueryKey(workspaceId),
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
export type ProductListQuery = NonNullable<
  operations["list_products_v1_workspaces__workspace_id__products_get"]["parameters"]["query"]
>;

/**
 * One page of the product list as the screen asks for it (search by name or description, status, collection, sort). The previous page stays on screen while the next one loads; mutations reload it (same key
 * prefix as the full list).
 */
export function useProductPage(workspaceId: string, query: ProductListQuery) {
  return useQuery({
    queryKey: [...productsQueryKey(workspaceId), "page", query],
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

function useRefreshProducts(workspaceId: string) {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: productsQueryKey(workspaceId) });
}

/**
 * `POST .../products/{product_id}/duplicate` (201, editor or above): a new product with the
 * original's configuration, named "<nome> (cópia)" by the API. The webhook secret is not copied.
 */
export function useDuplicateProduct(workspaceId: string) {
  const refresh = useRefreshProducts(workspaceId);
  return useMutation({
    mutationFn: async (productId: string) =>
      unwrap(
        await apiClient.POST("/v1/workspaces/{workspace_id}/products/{product_id}/duplicate", {
          params: { path: { workspace_id: workspaceId, product_id: productId } },
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
export function useCreateProduct(workspaceId: string) {
  const refresh = useRefreshProducts(workspaceId);
  return useMutation({
    mutationFn: async (body: ProductInput) =>
      unwrap(
        await apiClient.POST("/v1/workspaces/{workspace_id}/products", {
          params: { path: { workspace_id: workspaceId } },
          body,
        }),
      ),
    onSuccess: refresh,
  });
}

export interface ProductUpdate {
  productId: string;
  changes: ProductChanges;
}

/**
 * `PATCH /v1/workspaces/{id}/products/{product_id}`; an empty `no_source_message` restores
 * the default message.
 */
export function useUpdateProduct(workspaceId: string) {
  const refresh = useRefreshProducts(workspaceId);
  return useMutation({
    mutationFn: async ({ productId, changes }: ProductUpdate) =>
      unwrap(
        await apiClient.PATCH("/v1/workspaces/{workspace_id}/products/{product_id}", {
          params: { path: { workspace_id: workspaceId, product_id: productId } },
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
  const refresh = useRefreshProducts(workspaceId);
  return useMutation({
    mutationFn: async (productId: string) =>
      unwrap(
        await apiClient.POST(
          "/v1/workspaces/{workspace_id}/products/{product_id}/ticket-webhook/secret",
          { params: { path: { workspace_id: workspaceId, product_id: productId } } },
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
    mutationFn: async (productId: string) =>
      unwrap(
        await apiClient.POST(
          "/v1/workspaces/{workspace_id}/products/{product_id}/ticket-webhook/test",
          { params: { path: { workspace_id: workspaceId, product_id: productId } } },
        ),
      ),
  });
}

/**
 * `DELETE /v1/workspaces/{id}/products/{product_id}` (204). The product's conversations go
 * with it; deactivating keeps them.
 */
export function useDeleteProduct(workspaceId: string) {
  const refresh = useRefreshProducts(workspaceId);
  return useMutation({
    mutationFn: async (productId: string) => {
      unwrap(
        await apiClient.DELETE("/v1/workspaces/{workspace_id}/products/{product_id}", {
          params: { path: { workspace_id: workspaceId, product_id: productId } },
        }),
      );
    },
    onSuccess: refresh,
  });
}
