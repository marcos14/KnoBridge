import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient, unwrap } from "./client";
import { fetchAllPages } from "./pages";
import type { components } from "./schema.gen";

export type HarnessModule = components["schemas"]["HarnessModuleOut"];
export type HarnessModuleInput = components["schemas"]["HarnessModuleCreate"];
export type HarnessModuleChanges = components["schemas"]["HarnessModuleUpdate"];
export type HarnessJob = components["schemas"]["HarnessJobOut"];
export type HarnessJobDetail = components["schemas"]["HarnessJobDetailOut"];
export type HarnessJobStatus = components["schemas"]["HarnessJobStatus"];
export type HarnessJobBatch = components["schemas"]["HarnessJobBatchIn"];
export type HarnessJobSkipped = components["schemas"]["HarnessJobSkipped"];
export type HarnessRejection = components["schemas"]["HarnessRejectionOut"];

/**
 * How often the module and job screens ask again while a job has not finished. A job takes
 * minutes and the runner reports every 30 s, so a few seconds is enough.
 */
export const HARNESS_POLL_INTERVAL_MS = 5000;

/**
 * Whether a job may still change: the statuses the server counts as `already_queued` (queued,
 * leased, running, deferred). `null` (a module that never ran) is not active.
 */
export function isHarnessJobActive(status: HarnessJobStatus | null | undefined): boolean {
  return (
    status === "queued" || status === "leased" || status === "running" || status === "deferred"
  );
}

function harnessPoll(active: boolean): number | false {
  return active ? HARNESS_POLL_INTERVAL_MS : false;
}

function harnessRootKey(workspaceId: string) {
  return ["api", "workspaces", workspaceId, "harness"] as const;
}

export function harnessModulesQueryKey(workspaceId: string, sourceId: string) {
  return [...harnessRootKey(workspaceId), "sources", sourceId, "modules"] as const;
}

export interface HarnessPage {
  limit: number;
  offset: number;
}

/**
 * Every module of a runner source, by key (any member). A repository has up to 2000 modules: the
 * screen filters and pages them in the browser. Polls while a module's last job is active, so its
 * status and mapped commit follow the runner.
 */
export function useHarnessModules(workspaceId: string, sourceId: string) {
  return useQuery({
    queryKey: harnessModulesQueryKey(workspaceId, sourceId),
    queryFn: ({ signal }) =>
      fetchAllPages(async (page) =>
        unwrap(
          await apiClient.GET("/v1/workspaces/{workspace_id}/sources/{source_id}/modules", {
            params: { path: { workspace_id: workspaceId, source_id: sourceId }, query: page },
            signal,
          }),
        ),
      ),
    refetchInterval: (query) =>
      harnessPoll(
        query.state.data?.some((module) => isHarnessJobActive(module.last_job_status)) ?? false,
      ),
  });
}

/** One page of the source's jobs, newest first; polls while one of them is active. */
export function useHarnessJobs(workspaceId: string, sourceId: string, page: HarnessPage) {
  return useQuery({
    queryKey: [...harnessRootKey(workspaceId), "sources", sourceId, "jobs", page],
    queryFn: async ({ signal }) =>
      unwrap(
        await apiClient.GET("/v1/workspaces/{workspace_id}/sources/{source_id}/harness-jobs", {
          params: { path: { workspace_id: workspaceId, source_id: sourceId }, query: page },
          signal,
        }),
      ),
    placeholderData: keepPreviousData,
    refetchInterval: (query) =>
      harnessPoll(query.state.data?.items.some((job) => isHarnessJobActive(job.status)) ?? false),
  });
}

/**
 * One job with a page of the items the runner's verification rejected
 * (`rejections_limit`/`rejections_offset`); 404 `job_not_found`. Polls while it is active.
 */
export function useHarnessJob(workspaceId: string, jobId: string, rejections: HarnessPage) {
  return useQuery({
    queryKey: [...harnessRootKey(workspaceId), "jobs", jobId, rejections],
    queryFn: async ({ signal }) =>
      unwrap(
        await apiClient.GET("/v1/workspaces/{workspace_id}/harness-jobs/{job_id}", {
          params: {
            path: { workspace_id: workspaceId, job_id: jobId },
            query: { rejections_limit: rejections.limit, rejections_offset: rejections.offset },
          },
          signal,
        }),
      ),
    placeholderData: keepPreviousData,
    refetchInterval: (query) => harnessPoll(isHarnessJobActive(query.state.data?.status)),
  });
}

/** Reloads every module and job query of the workspace (the polling follows the new data). */
function useRefreshHarness(workspaceId: string) {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: harnessRootKey(workspaceId) });
}

/**
 * `POST .../sources/{source_id}/modules` (201, editor): a manual module (`suggested = false`;
 * without `key`, derived from the title). 409 `module_key_taken`.
 */
export function useCreateHarnessModule(workspaceId: string, sourceId: string) {
  const refresh = useRefreshHarness(workspaceId);
  return useMutation({
    mutationFn: async (body: HarnessModuleInput) =>
      unwrap(
        await apiClient.POST("/v1/workspaces/{workspace_id}/sources/{source_id}/modules", {
          params: { path: { workspace_id: workspaceId, source_id: sourceId } },
          body,
        }),
      ),
    onSuccess: refresh,
  });
}

export interface HarnessModuleUpdate {
  moduleId: string;
  changes: HarnessModuleChanges;
}

/**
 * `PATCH .../modules/{module_id}` (editor): title, patterns and/or `enabled`. Changing title or
 * patterns makes the module manual (`suggested = false`). 404 `module_not_found`.
 */
export function useUpdateHarnessModule(workspaceId: string, sourceId: string) {
  const refresh = useRefreshHarness(workspaceId);
  return useMutation({
    mutationFn: async ({ moduleId, changes }: HarnessModuleUpdate) =>
      unwrap(
        await apiClient.PATCH(
          "/v1/workspaces/{workspace_id}/sources/{source_id}/modules/{module_id}",
          {
            params: {
              path: { workspace_id: workspaceId, source_id: sourceId, module_id: moduleId },
            },
            body: changes,
          },
        ),
      ),
    onSuccess: refresh,
  });
}

/**
 * `POST .../sources/{source_id}/harness-jobs` (202, editor): one manual job per enabled module
 * without an active job; the others come back in `skipped` (`already_queued`, `module_disabled`).
 * Without `executor`/`model`, the source's. 409 `source_inactive`; 404 `module_not_found`.
 */
export function useEnqueueHarnessJobs(workspaceId: string, sourceId: string) {
  const refresh = useRefreshHarness(workspaceId);
  return useMutation({
    mutationFn: async (body: HarnessJobBatch) =>
      unwrap(
        await apiClient.POST("/v1/workspaces/{workspace_id}/sources/{source_id}/harness-jobs", {
          params: { path: { workspace_id: workspaceId, source_id: sourceId } },
          body,
        }),
      ),
    onSuccess: refresh,
  });
}

/** `POST .../harness-jobs/{job_id}/cancel` (200 with the job, editor); 409 `job_finished`. */
export function useCancelHarnessJob(workspaceId: string) {
  const refresh = useRefreshHarness(workspaceId);
  return useMutation({
    mutationFn: async (jobId: string) =>
      unwrap(
        await apiClient.POST("/v1/workspaces/{workspace_id}/harness-jobs/{job_id}/cancel", {
          params: { path: { workspace_id: workspaceId, job_id: jobId } },
        }),
      ),
    onSuccess: refresh,
  });
}
