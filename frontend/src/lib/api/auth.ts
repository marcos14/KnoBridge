import { hashKey, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient, toApiError, unwrap } from "./client";
import { apiHealthQueryKey } from "./health";
import type { components } from "./schema.gen";

export type Me = components["schemas"]["MeResponse"];
export type UserWorkspace = components["schemas"]["UserWorkspaceOut"];
export type Role = components["schemas"]["Role"];
export type LoginInput = components["schemas"]["LoginRequest"];

export const meQueryKey = ["api", "me"] as const;
export const setupStatusQueryKey = ["api", "setup", "status"] as const;

/** Who is logged in (`GET /v1/me`), or `null` when nobody is (401). */
export async function fetchMe(signal?: AbortSignal): Promise<Me | null> {
  const result = await apiClient.GET("/v1/me", { signal });
  if (result.response.status === 401) {
    return null;
  }
  return unwrap(result);
}

/** Current user and workspaces; `data === null` means anonymous. */
export function useMe() {
  return useQuery({
    queryKey: meQueryKey,
    queryFn: ({ signal }) => fetchMe(signal),
  });
}

/** `POST /v1/auth/login`; the answer is the body of `/v1/me`, which fills the `useMe` cache. */
export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: LoginInput) =>
      unwrap(await apiClient.POST("/v1/auth/login", { body })),
    onSuccess: (me) => {
      queryClient.setQueryData(meQueryKey, me);
    },
  });
}

/** Queries that do not belong to a user and survive a logout. */
const ANONYMOUS_QUERY_HASHES = new Set(
  [meQueryKey, setupStatusQueryKey, apiHealthQueryKey].map((key) => hashKey(key)),
);

/**
 * `POST /v1/auth/logout`. A 401 means the session had already ended, which is the goal too.
 * Afterwards `useMe` answers `null` and every user-scoped query is dropped from the cache.
 */
export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { error, response } = await apiClient.POST("/v1/auth/logout");
      if (!response.ok && response.status !== 401) {
        throw toApiError(response.status, error);
      }
    },
    onSuccess: () => {
      queryClient.setQueryData(meQueryKey, null);
      queryClient.removeQueries({
        predicate: (query) => !ANONYMOUS_QUERY_HASHES.has(query.queryHash),
      });
    },
  });
}
