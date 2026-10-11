import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient, unwrap } from "./client";
import { collectionsQueryKey } from "./collections";
import { fetchAllPages } from "./pages";
import type { components } from "./schema.gen";

export type Source = components["schemas"]["SourceOut"];
export type SourceKind = components["schemas"]["SourceKind"];
export type SourceInput = components["schemas"]["SourceCreate"];
export type SourceChanges = components["schemas"]["SourceUpdate"];
export type SourceTestResult = components["schemas"]["SourceTestResult"];
export type Run = components["schemas"]["RunOut"];
export type RunDetail = components["schemas"]["RunDetailOut"];
export type RunError = components["schemas"]["RunErrorOut"];
export type RunErrorStage = components["schemas"]["RunErrorStage"];
export type RunStatus = components["schemas"]["RunStatus"];
export type RunTrigger = components["schemas"]["RunTrigger"];
export type SourceDocument = components["schemas"]["DocumentOut"];
export type DocumentKind = components["schemas"]["DocumentKind"];

/** How often a screen asks again while a run is queued or running. */
export const RUN_POLL_INTERVAL_MS = 3000;

/** Whether a run has not finished yet (the worker may still change it). */
export function isRunActive(status: RunStatus | undefined): boolean {
  return status === "queued" || status === "running";
}

/** `refetchInterval` of a query: polls while `active` says the data is still moving. */
export function pollWhile(active: boolean): number | false {
  return active ? RUN_POLL_INTERVAL_MS : false;
}

function sourcesRootKey(workspaceId: string) {
  return ["api", "workspaces", workspaceId, "sources"] as const;
}

export function sourcesQueryKey(workspaceId: string, collectionId?: string) {
  return [...sourcesRootKey(workspaceId), { collectionId }] as const;
}

export function sourceQueryKey(workspaceId: string, sourceId: string) {
  return [...sourcesRootKey(workspaceId), sourceId] as const;
}

function runsRootKey(workspaceId: string) {
  return ["api", "workspaces", workspaceId, "runs"] as const;
}

/**
 * Every source of the workspace (any member), ordered by name, with its last run; only those of
 * `collectionId` when given (filtered by the API). Polls while any of them is syncing.
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
    refetchInterval: (query) =>
      pollWhile(query.state.data?.some((item) => isRunActive(item.last_run?.status)) ?? false),
  });
}

/** One source with its last run; 404 `source_not_found`. Polls while its last run is active. */
export function useSource(workspaceId: string, sourceId: string) {
  return useQuery({
    queryKey: sourceQueryKey(workspaceId, sourceId),
    queryFn: async ({ signal }) =>
      unwrap(
        await apiClient.GET("/v1/workspaces/{workspace_id}/sources/{source_id}", {
          params: { path: { workspace_id: workspaceId, source_id: sourceId } },
          signal,
        }),
      ),
    refetchInterval: (query) => pollWhile(isRunActive(query.state.data?.last_run?.status)),
  });
}

export interface PageQuery {
  limit: number;
  offset: number;
}

/** One page of the source's runs, newest first; polls while one of them is active. */
export function useSourceRuns(workspaceId: string, sourceId: string, page: PageQuery) {
  return useQuery({
    queryKey: [...sourceQueryKey(workspaceId, sourceId), "runs", page],
    queryFn: async ({ signal }) =>
      unwrap(
        await apiClient.GET("/v1/workspaces/{workspace_id}/sources/{source_id}/runs", {
          params: { path: { workspace_id: workspaceId, source_id: sourceId }, query: page },
          signal,
        }),
      ),
    placeholderData: keepPreviousData,
    refetchInterval: (query) =>
      pollWhile(query.state.data?.items.some((run) => isRunActive(run.status)) ?? false),
  });
}

/**
 * One run with a page of its per-document errors (`errors_limit`/`errors_offset`); 404
 * `run_not_found`. Polls while it is active (errors keep arriving).
 */
export function useRun(workspaceId: string, runId: string, errors: PageQuery) {
  return useQuery({
    queryKey: [...runsRootKey(workspaceId), runId, errors],
    queryFn: async ({ signal }) =>
      unwrap(
        await apiClient.GET("/v1/workspaces/{workspace_id}/runs/{run_id}", {
          params: {
            path: { workspace_id: workspaceId, run_id: runId },
            query: { errors_limit: errors.limit, errors_offset: errors.offset },
          },
          signal,
        }),
      ),
    placeholderData: keepPreviousData,
    refetchInterval: (query) => pollWhile(isRunActive(query.state.data?.status)),
  });
}

/** Filters of the indexed documents of a source; `path` (never blank) matches inside the key. */
export interface DocumentQuery extends PageQuery {
  path?: string;
  kind?: DocumentKind;
}

/** One page of the documents indexed from the source, with their chunk counts. */
export function useSourceDocuments(workspaceId: string, sourceId: string, query: DocumentQuery) {
  const { path, kind, limit, offset } = query;
  return useQuery({
    queryKey: [...sourceQueryKey(workspaceId, sourceId), "documents", query],
    queryFn: async ({ signal }) =>
      unwrap(
        await apiClient.GET("/v1/workspaces/{workspace_id}/sources/{source_id}/documents", {
          params: {
            path: { workspace_id: workspaceId, source_id: sourceId },
            query: {
              path,
              path_match: "contains",
              kind,
              limit,
              offset,
            },
          },
          signal,
        }),
      ),
    placeholderData: keepPreviousData,
  });
}

/**
 * Reloads every source query (list, detail, runs, documents) and runs; with `collections`, also
 * the collections, whose source counts change when a source is created or deleted.
 */
function useRefreshSources(workspaceId: string, { collections = false } = {}) {
  const queryClient = useQueryClient();
  return async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: sourcesRootKey(workspaceId) }),
      queryClient.invalidateQueries({ queryKey: runsRootKey(workspaceId) }),
      collections
        ? queryClient.invalidateQueries({ queryKey: collectionsQueryKey(workspaceId) })
        : undefined,
    ]);
  };
}

/**
 * `POST /v1/workspaces/{id}/sources` (201). 409 `source_name_taken`; 422 `source_config_invalid`,
 * `source_schedule_invalid` or `source_collection_invalid`.
 */
export function useCreateSource(workspaceId: string) {
  const refresh = useRefreshSources(workspaceId, { collections: true });
  return useMutation({
    mutationFn: async (body: SourceInput) =>
      unwrap(
        await apiClient.POST("/v1/workspaces/{workspace_id}/sources", {
          params: { path: { workspace_id: workspaceId } },
          body,
        }),
      ),
    onSuccess: refresh,
  });
}

export interface SourceUpdate {
  sourceId: string;
  changes: SourceChanges;
}

/**
 * `PATCH /v1/workspaces/{id}/sources/{source_id}`: the fields sent change (`config` whole,
 * `schedule_cron: null` clears it); kind and collection never change.
 */
export function useUpdateSource(workspaceId: string) {
  const refresh = useRefreshSources(workspaceId);
  return useMutation({
    mutationFn: async ({ sourceId, changes }: SourceUpdate) =>
      unwrap(
        await apiClient.PATCH("/v1/workspaces/{workspace_id}/sources/{source_id}", {
          params: { path: { workspace_id: workspaceId, source_id: sourceId } },
          body: changes,
        }),
      ),
    onSuccess: refresh,
  });
}

/** `DELETE /v1/workspaces/{id}/sources/{source_id}` (204): its documents and chunks go too. */
export function useDeleteSource(workspaceId: string) {
  const refresh = useRefreshSources(workspaceId, { collections: true });
  return useMutation({
    mutationFn: async (sourceId: string) => {
      unwrap(
        await apiClient.DELETE("/v1/workspaces/{workspace_id}/sources/{source_id}", {
          params: { path: { workspace_id: workspaceId, source_id: sourceId } },
        }),
      );
    },
    onSuccess: refresh,
  });
}

/**
 * `POST .../{source_id}/test`: reads the source without indexing. A source failure is still a
 * 200, with `ok: false` and the error `code`. Changes nothing, so it refreshes nothing.
 */
export function useTestSource(workspaceId: string) {
  return useMutation({
    mutationFn: async (sourceId: string) =>
      unwrap(
        await apiClient.POST("/v1/workspaces/{workspace_id}/sources/{source_id}/test", {
          params: { path: { workspace_id: workspaceId, source_id: sourceId } },
        }),
      ),
  });
}

/**
 * `POST .../{source_id}/sync` (202 with the queued run). 409 `sync_already_running` or
 * `source_inactive`; 503 `sync_unavailable`. The reload starts the polling.
 */
export function useSyncSource(workspaceId: string) {
  const refresh = useRefreshSources(workspaceId);
  return useMutation({
    mutationFn: async (sourceId: string) =>
      unwrap(
        await apiClient.POST("/v1/workspaces/{workspace_id}/sources/{source_id}/sync", {
          params: { path: { workspace_id: workspaceId, source_id: sourceId } },
        }),
      ),
    onSuccess: refresh,
  });
}

/** `POST .../{source_id}/cancel` (202 with the run); 409 `sync_not_running`. */
export function useCancelSync(workspaceId: string) {
  const refresh = useRefreshSources(workspaceId);
  return useMutation({
    mutationFn: async (sourceId: string) =>
      unwrap(
        await apiClient.POST("/v1/workspaces/{workspace_id}/sources/{source_id}/cancel", {
          params: { path: { workspace_id: workspaceId, source_id: sourceId } },
        }),
      ),
    onSuccess: refresh,
  });
}
