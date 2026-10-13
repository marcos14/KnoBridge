import {
  hashKey,
  type QueryClient,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { apiClient, toApiError, unwrap } from "./client";
import { apiHealthQueryKey } from "./health";
import type { components } from "./schema.gen";

export type Me = components["schemas"]["MeResponse"];
export type UserWorkspace = components["schemas"]["UserWorkspaceOut"];
export type Role = components["schemas"]["Role"];
export type LoginInput = components["schemas"]["LoginRequest"];

export const meQueryKey = ["api", "me"] as const;
export const setupStatusQueryKey = ["api", "setup", "status"] as const;
/**
 * Client-only marker (no request behind it): `true` after the user logged out in this tab, until
 * the next login or setup. Tells the guards the anonymous state was asked for, not a session that
 * expired, so they send to a plain `/login` instead of `/login?next=<page>`.
 */
export const loggedOutQueryKey = ["api", "auth", "loggedOut"] as const;

/** Whether the current anonymous state comes from an explicit logout in this tab. */
export function useLoggedOutByUser(): boolean {
  return useQueryClient().getQueryData<boolean>(loggedOutQueryKey) === true;
}

/** Stores a fresh session (login or setup answer) and forgets a previous logout. */
export function storeSession(queryClient: QueryClient, me: Me): void {
  queryClient.removeQueries({ queryKey: loggedOutQueryKey, exact: true });
  queryClient.setQueryData(meQueryKey, me);
}

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
      storeSession(queryClient, me);
    },
  });
}

/** Fields of `PATCH /v1/me`; omitted ones keep their value. */
export type ProfileUpdate = components["schemas"]["ProfileUpdate"];

/** Copy of `me` with the non-null fields of `update` applied to the user. */
function withProfileUpdate(me: Me, update: ProfileUpdate): Me {
  const changed = Object.fromEntries(Object.entries(update).filter(([, value]) => value !== null));
  return { ...me, user: { ...me.user, ...changed } };
}

/**
 * `PATCH /v1/me`. Optimistic: the `useMe` cache changes at once (the theme switches without
 * waiting for the server), goes back to the previous value on error and takes the answer, which
 * is the body of `/v1/me`, on success.
 */
export function useUpdateProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: ProfileUpdate) => unwrap(await apiClient.PATCH("/v1/me", { body })),
    onMutate: async (update) => {
      await queryClient.cancelQueries({ queryKey: meQueryKey });
      const previous = queryClient.getQueryData<Me | null>(meQueryKey);
      if (previous) {
        queryClient.setQueryData<Me>(meQueryKey, withProfileUpdate(previous, update));
      }
      return { previous };
    },
    onError: (_error, _update, context) => {
      queryClient.setQueryData(meQueryKey, context?.previous);
    },
    onSuccess: (me) => {
      queryClient.setQueryData(meQueryKey, me);
    },
  });
}

/** Queries that do not belong to a user and survive a logout. */
const ANONYMOUS_QUERY_HASHES = new Set(
  [meQueryKey, setupStatusQueryKey, apiHealthQueryKey, loggedOutQueryKey].map((key) =>
    hashKey(key),
  ),
);

/**
 * Forgets the session the user ended in this tab (logout, or revoking this session on the security
 * page): `useMe` answers `null`, `useLoggedOutByUser` answers `true` and every user-scoped query
 * leaves the cache.
 */
export function endSession(queryClient: QueryClient): void {
  // Marker first: the guards that react to `me === null` must already see it.
  queryClient.setQueryData(loggedOutQueryKey, true);
  queryClient.setQueryData(meQueryKey, null);
  queryClient.removeQueries({
    predicate: (query) => !ANONYMOUS_QUERY_HASHES.has(query.queryHash),
  });
}

/**
 * `POST /v1/auth/logout-all`: ends every session of the user, this one included. A 401 means this
 * session had already ended, which still leaves the tab logged out. Afterwards, as after a logout,
 * `useMe` answers `null` and the guards send the user to the login.
 */
export function useLogoutAll() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { error, response } = await apiClient.POST("/v1/auth/logout-all");
      if (!response.ok && response.status !== 401) {
        throw toApiError(response.status, error);
      }
    },
    onSuccess: () => {
      endSession(queryClient);
    },
  });
}

/**
 * `POST /v1/auth/logout`. A 401 means the session had already ended, which is the goal too.
 * Afterwards `useMe` answers `null`, `useLoggedOutByUser` answers `true` and every user-scoped
 * query is dropped from the cache.
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
      endSession(queryClient);
    },
  });
}
