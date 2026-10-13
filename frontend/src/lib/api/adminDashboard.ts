import { useQuery } from "@tanstack/react-query";

import { apiClient, unwrap } from "./client";
import type { components } from "./schema.gen";

export type InstanceDashboard = components["schemas"]["InstanceDashboardOut"];
export type InstanceHealth = components["schemas"]["InstanceHealthOut"];
export type ServiceCheck = components["schemas"]["ServiceCheckOut"];
export type ServiceStatus = components["schemas"]["ServiceStatus"];

export const instanceDashboardQueryKey = ["api", "admin", "dashboard"] as const;
export const instanceHealthQueryKey = ["api", "admin", "health"] as const;

/** Counts, recent failures and usage of the instance (`GET /v1/admin/dashboard`, last 30 days). */
export function useInstanceDashboard() {
  return useQuery({
    queryKey: instanceDashboardQueryKey,
    queryFn: async ({ signal }) => unwrap(await apiClient.GET("/v1/admin/dashboard", { signal })),
  });
}

/**
 * Health of API, database, Temporal and worker (`GET /v1/admin/health`). Separate from the
 * dashboard so the numbers do not wait for the checks; always 200, the state is in the body.
 */
export function useInstanceHealth() {
  return useQuery({
    queryKey: instanceHealthQueryKey,
    queryFn: async ({ signal }) => unwrap(await apiClient.GET("/v1/admin/health", { signal })),
  });
}
