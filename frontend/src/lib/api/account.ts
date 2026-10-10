import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { endSession, meQueryKey } from "./auth";
import { apiClient, isApiErrorCode, toApiError, unwrap } from "./client";
import type { components } from "./schema.gen";

export type Session = components["schemas"]["SessionOut"];
export type ChangePasswordInput = components["schemas"]["ChangePasswordRequest"];

export const sessionsQueryKey = ["api", "me", "sessions"] as const;

/** Largest page `GET /v1/me/sessions` accepts. */
const SESSIONS_PAGE_SIZE = 100;

/** Every live session of the user, most recently used first, reading as many pages as needed. */
export async function fetchSessions(signal?: AbortSignal): Promise<Session[]> {
  const sessions: Session[] = [];
  for (;;) {
    const page = unwrap(
      await apiClient.GET("/v1/me/sessions", {
        params: { query: { limit: SESSIONS_PAGE_SIZE, offset: sessions.length } },
        signal,
      }),
    );
    sessions.push(...page.items);
    if (page.items.length === 0 || sessions.length >= page.total) {
      return sessions;
    }
  }
}

/** Live sessions of the logged-in user; `current` marks the one of this browser. */
export function useSessions() {
  return useQuery({
    queryKey: sessionsQueryKey,
    queryFn: ({ signal }) => fetchSessions(signal),
  });
}

/** `DELETE /v1/me/sessions/{id}`; a 404 means the session had already ended, which is the goal. */
async function deleteSession(sessionId: string): Promise<void> {
  const { error, response } = await apiClient.DELETE("/v1/me/sessions/{session_id}", {
    params: { path: { session_id: sessionId } },
  });
  if (!response.ok && response.status !== 404) {
    throw toApiError(response.status, error);
  }
}

/**
 * Ends one session. Ending the current one is a logout here: the backend clears the cookies and
 * the cache forgets the user, so the guards send to a plain `/login`.
 */
export function useRevokeSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (session: Pick<Session, "id" | "current">) => deleteSession(session.id),
    onSuccess: (_data, session) => {
      if (session.current) {
        endSession(queryClient);
        return undefined;
      }
      return queryClient.invalidateQueries({ queryKey: sessionsQueryKey });
    },
  });
}

/**
 * Ends every session except this one. The API has no single call for it (`POST
 * /v1/auth/logout-all` ends this one too), so each other session is revoked on its own, from a
 * fresh list, so a session opened after the page loaded also ends.
 */
export function useRevokeOtherSessions() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const others = (await fetchSessions()).filter((session) => !session.current);
      await Promise.all(others.map((session) => deleteSession(session.id)));
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: sessionsQueryKey }),
  });
}

/**
 * `POST /v1/me/password` (204). The backend ends every other session and keeps this one, so the
 * session list is refreshed.
 */
export function useChangePassword() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: ChangePasswordInput) => {
      unwrap(await apiClient.POST("/v1/me/password", { body }));
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: sessionsQueryKey }),
  });
}

/**
 * `POST /v1/auth/email/resend` (204). A 409 `email_already_verified` means `me` is stale (the
 * link was opened elsewhere), so it is refreshed.
 */
export function useResendVerification() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      unwrap(await apiClient.POST("/v1/auth/email/resend"));
    },
    onError: (error) => {
      if (isApiErrorCode(error, "email_already_verified")) {
        return queryClient.invalidateQueries({ queryKey: meQueryKey });
      }
      return undefined;
    },
  });
}
