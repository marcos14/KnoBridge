import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient, unwrap } from "./client";
import { fetchAllPages } from "./pages";
import type { components, operations } from "./schema.gen";

export type Widget = components["schemas"]["WidgetOut"];
export type WidgetInput = components["schemas"]["WidgetCreate"];
export type WidgetChanges = components["schemas"]["WidgetUpdate"];
export type WidgetSigningSecret = components["schemas"]["WidgetSigningSecretOut"];
export type WidgetMode = components["schemas"]["WidgetMode"];
export type WidgetPosition = components["schemas"]["WidgetPosition"];
export type WidgetTheme = components["schemas"]["WidgetTheme"];

/** Query of `GET .../widgets`: `query` (name), `product_id`, `active`, `limit`, `offset`. */
export type WidgetListQuery = NonNullable<
  operations["list_widgets_v1_workspaces__workspace_id__widgets_get"]["parameters"]["query"]
>;

export function widgetsQueryKey(workspaceId: string) {
  return ["api", "workspaces", workspaceId, "widgets"] as const;
}

/** Every widget of the workspace, ordered by name (owner or admin), for filters of other screens. */
export function useWidgets(workspaceId: string) {
  return useQuery({
    queryKey: [...widgetsQueryKey(workspaceId), "all"],
    queryFn: ({ signal }) =>
      fetchAllPages(async (query) =>
        unwrap(
          await apiClient.GET("/v1/workspaces/{workspace_id}/widgets", {
            params: { path: { workspace_id: workspaceId }, query },
            signal,
          }),
        ),
      ),
  });
}

/** One page of the widget list, searched and filtered by the API. */
export function useWidgetPage(workspaceId: string, query: WidgetListQuery) {
  return useQuery({
    queryKey: [...widgetsQueryKey(workspaceId), "page", query],
    queryFn: async ({ signal }) =>
      unwrap(
        await apiClient.GET("/v1/workspaces/{workspace_id}/widgets", {
          params: { path: { workspace_id: workspaceId }, query },
          signal,
        }),
      ),
    placeholderData: keepPreviousData,
  });
}

/** `GET .../widgets/{widget_id}`; 404 `not_found`. */
export function useWidget(workspaceId: string, widgetId: string) {
  return useQuery({
    queryKey: [...widgetsQueryKey(workspaceId), "detail", widgetId],
    queryFn: async ({ signal }) =>
      unwrap(
        await apiClient.GET("/v1/workspaces/{workspace_id}/widgets/{widget_id}", {
          params: { path: { workspace_id: workspaceId, widget_id: widgetId } },
          signal,
        }),
      ),
  });
}

function useRefreshWidgets(workspaceId: string) {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: widgetsQueryKey(workspaceId) });
}

/**
 * `POST .../widgets` (201) with the product, name and allowed origins (the rest takes the
 * defaults). 409 `widget_name_taken`; 422 `widget_product_invalid` or `widget_origin_invalid`.
 */
export function useCreateWidget(workspaceId: string) {
  const refresh = useRefreshWidgets(workspaceId);
  return useMutation({
    mutationFn: async (body: WidgetInput) =>
      unwrap(
        await apiClient.POST("/v1/workspaces/{workspace_id}/widgets", {
          params: { path: { workspace_id: workspaceId } },
          body,
        }),
      ),
    onSuccess: refresh,
  });
}

export interface WidgetUpdate {
  widgetId: string;
  changes: WidgetChanges;
}

/** `PATCH .../widgets/{widget_id}`: only what changed (`title: null` is the product's name). */
export function useUpdateWidget(workspaceId: string) {
  const refresh = useRefreshWidgets(workspaceId);
  return useMutation({
    mutationFn: async ({ widgetId, changes }: WidgetUpdate) =>
      unwrap(
        await apiClient.PATCH("/v1/workspaces/{workspace_id}/widgets/{widget_id}", {
          params: { path: { workspace_id: workspaceId, widget_id: widgetId } },
          body: changes,
        }),
      ),
    onSuccess: refresh,
  });
}

/** `DELETE .../widgets/{widget_id}` (204): the widget's conversations go with it. */
export function useDeleteWidget(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (widgetId: string) => {
      unwrap(
        await apiClient.DELETE("/v1/workspaces/{workspace_id}/widgets/{widget_id}", {
          params: { path: { workspace_id: workspaceId, widget_id: widgetId } },
        }),
      );
    },
    onSuccess: async (_, widgetId) => {
      // The detail would answer 404 now: drop it instead of refetching it.
      queryClient.removeQueries({
        queryKey: [...widgetsQueryKey(workspaceId), "detail", widgetId],
      });
      await queryClient.invalidateQueries({ queryKey: widgetsQueryKey(workspaceId) });
    },
  });
}

/**
 * `POST .../widgets/{widget_id}/signing-secret` (201): generates or replaces the `kbs_` secret,
 * returned this once; identities signed with the previous one are refused from now on.
 */
export function useRotateWidgetSigningSecret(workspaceId: string) {
  const refresh = useRefreshWidgets(workspaceId);
  return useMutation({
    mutationFn: async (widgetId: string) =>
      unwrap(
        await apiClient.POST("/v1/workspaces/{workspace_id}/widgets/{widget_id}/signing-secret", {
          params: { path: { workspace_id: workspaceId, widget_id: widgetId } },
        }),
      ),
    onSuccess: refresh,
  });
}

/** `DELETE .../widgets/{widget_id}/signing-secret` (204): signed identities stop working. */
export function useRemoveWidgetSigningSecret(workspaceId: string) {
  const refresh = useRefreshWidgets(workspaceId);
  return useMutation({
    mutationFn: async (widgetId: string) => {
      unwrap(
        await apiClient.DELETE("/v1/workspaces/{workspace_id}/widgets/{widget_id}/signing-secret", {
          params: { path: { workspace_id: workspaceId, widget_id: widgetId } },
        }),
      );
    },
    onSuccess: refresh,
  });
}
