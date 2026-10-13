import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";

import { attachmentFilename, saveBlob } from "../download";
import { apiClient, unwrap } from "./client";
import type { components } from "./schema.gen";

/** Usage and costs of a workspace (`docs/specs/uso-e-custos.md`), for owners and admins. */
export type UsageGroup = components["schemas"]["UsageGroup"];
export type UsageReport = components["schemas"]["UsageReportOut"];
export type UsageRow = components["schemas"]["UsageRowOut"];
export type UsageTotals = components["schemas"]["UsageTotalsOut"];

/** Grouping and period `[from, to)` (ISO 8601 instants; missing = the API's default). */
export interface UsageQuery {
  groupBy: UsageGroup;
  from?: string;
  to?: string;
}

export function usageQueryKey(workspaceId: string) {
  return ["api", "workspaces", workspaceId, "usage"] as const;
}

function usageParams(workspaceId: string, query: UsageQuery) {
  return {
    path: { workspace_id: workspaceId },
    query: { group_by: query.groupBy, from: query.from, to: query.to },
  };
}

/** `GET .../usage`: totals of the period and one row per group (422 `usage_period_too_long`). */
export function useUsage(workspaceId: string, query: UsageQuery) {
  return useQuery({
    queryKey: [...usageQueryKey(workspaceId), query],
    queryFn: async ({ signal }) =>
      unwrap(
        await apiClient.GET("/v1/workspaces/{workspace_id}/usage", {
          params: usageParams(workspaceId, query),
          signal,
        }),
      ),
    placeholderData: keepPreviousData,
  });
}

/**
 * `GET .../usage.csv`: the same report as CSV, saved by the browser under the name of
 * `Content-Disposition` (without it, `knobridge-uso-<group>.csv`). Resolves with that name.
 */
export function useExportUsage(workspaceId: string) {
  return useMutation({
    mutationFn: async (query: UsageQuery) => {
      const result = await apiClient.GET("/v1/workspaces/{workspace_id}/usage.csv", {
        params: usageParams(workspaceId, query),
        parseAs: "blob",
      });
      const blob = unwrap(result);
      const filename =
        attachmentFilename(result.response.headers.get("Content-Disposition")) ??
        `knobridge-uso-${query.groupBy}.csv`;
      saveBlob(blob, filename);
      return filename;
    },
  });
}
