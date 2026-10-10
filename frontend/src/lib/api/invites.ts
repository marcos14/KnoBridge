import { skipToken, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { storeSession } from "./auth";
import { apiClient, unwrap } from "./client";
import type { components } from "./schema.gen";

export type InvitationPreview = components["schemas"]["InvitationPreviewOut"];
export type AcceptInvitationInput = components["schemas"]["AcceptInvitationRequest"];

export function invitationPreviewQueryKey(token: string) {
  return ["api", "invites", "preview", token] as const;
}

/**
 * What an invitation offers (`POST /v1/invites/preview`; POST only to keep the token out of the
 * URL, the token is not spent). Disabled while there is no token.
 */
export function useInvitationPreview(token: string | undefined) {
  return useQuery({
    queryKey: invitationPreviewQueryKey(token ?? ""),
    queryFn:
      token === undefined
        ? skipToken
        : async ({ signal }) =>
            unwrap(await apiClient.POST("/v1/invites/preview", { body: { token }, signal })),
    // A rejected token (400) stays rejected: retrying only delays the "invalid link" screen.
    retry: false,
  });
}

/**
 * `POST /v1/invites/accept`: joins the workspace. A new account is created and logged in by the
 * answer's cookies; either way the answer is the body of `/v1/me`, which fills the `useMe` cache.
 * An address that already has an account must be logged in first (401 `login_required`).
 */
export function useAcceptInvitation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: AcceptInvitationInput) =>
      unwrap(await apiClient.POST("/v1/invites/accept", { body })),
    onSuccess: (me) => {
      storeSession(queryClient, me);
    },
  });
}
