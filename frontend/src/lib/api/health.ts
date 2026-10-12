import { useQuery } from "@tanstack/react-query";

import { ApiError, apiClient } from "./client";
import type { components } from "./schema.gen";

export type ReadyResponse = components["schemas"]["ReadyResponse"];

export const apiHealthQueryKey = ["api", "health", "ready"] as const;

/** How often the status indicator re-checks the API. */
export const API_HEALTH_REFETCH_MS = 30_000;

export async function fetchApiHealth(signal?: AbortSignal): Promise<ReadyResponse> {
  const { data, response } = await apiClient.GET("/v1/health/ready", { signal });
  if (data === undefined) {
    throw new ApiError(response.status);
  }
  return data;
}

/** Readiness of the API (`GET /v1/health/ready`): `isSuccess` means the API and its database answer. */
export function useApiHealth() {
  return useQuery({
    queryKey: apiHealthQueryKey,
    queryFn: ({ signal }) => fetchApiHealth(signal),
    // A status indicator must report failure right away instead of retrying silently.
    retry: false,
    refetchInterval: API_HEALTH_REFETCH_MS,
  });
}
