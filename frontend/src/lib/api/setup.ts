import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { setupStatusQueryKey, storeSession } from "./auth";
import { apiClient, unwrap } from "./client";
import type { components } from "./schema.gen";

export type SetupStatus = components["schemas"]["SetupStatusResponse"];
export type SetupInput = components["schemas"]["SetupRequest"];

export async function fetchSetupStatus(signal?: AbortSignal): Promise<SetupStatus> {
  return unwrap(await apiClient.GET("/v1/setup/status", { signal }));
}

/** Whether the instance still needs its first setup (`GET /v1/setup/status`). */
export function useSetupStatus() {
  return useQuery({
    queryKey: setupStatusQueryKey,
    queryFn: ({ signal }) => fetchSetupStatus(signal),
    // Only the setup itself flips the flag, and useRunSetup updates the cache when it does.
    staleTime: Infinity,
  });
}

/**
 * `POST /v1/setup`: creates the first superadmin and logs them in. The answer is the body of
 * `/v1/me`, which fills the `useMe` cache; the setup status becomes "done".
 */
export function useRunSetup() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: SetupInput) => unwrap(await apiClient.POST("/v1/setup", { body })),
    onSuccess: (me) => {
      queryClient.setQueryData<SetupStatus>(setupStatusQueryKey, { needs_setup: false });
      storeSession(queryClient, me);
    },
  });
}
