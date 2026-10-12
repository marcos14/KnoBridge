import {
  keepPreviousData,
  skipToken,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

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

export type Invitation = components["schemas"]["InvitationOut"];
export type InviteInput = components["schemas"]["InviteRequest"];

export function workspaceInvitesQueryKey(workspaceId: string) {
  return ["api", "workspaces", workspaceId, "invites"] as const;
}

export interface PageRequest {
  limit: number;
  offset: number;
}

/** One page of the workspace's pending invitations, newest first (expired ones marked). */
export function useWorkspaceInvites(workspaceId: string, { limit, offset }: PageRequest) {
  return useQuery({
    queryKey: [...workspaceInvitesQueryKey(workspaceId), { limit, offset }],
    queryFn: async ({ signal }) =>
      unwrap(
        await apiClient.GET("/v1/workspaces/{workspace_id}/invites", {
          params: { path: { workspace_id: workspaceId }, query: { limit, offset } },
          signal,
        }),
      ),
    // Keeps the current page on screen while the next one loads.
    placeholderData: keepPreviousData,
  });
}

function useRefreshInvites(workspaceId: string) {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: workspaceInvitesQueryKey(workspaceId) });
}

/**
 * `POST /v1/workspaces/{id}/invites` (201). A pending invitation to the same address is replaced;
 * 409 `already_member` / `invitation_pending`, 403 `role_not_allowed`.
 */
export function useCreateInvite(workspaceId: string) {
  const refresh = useRefreshInvites(workspaceId);
  return useMutation({
    mutationFn: async (body: InviteInput) =>
      unwrap(
        await apiClient.POST("/v1/workspaces/{workspace_id}/invites", {
          params: { path: { workspace_id: workspaceId } },
          body,
        }),
      ),
    onSuccess: refresh,
  });
}

/** `DELETE /v1/workspaces/{id}/invites/{invitation_id}` (204): the link stops working. */
export function useRevokeInvite(workspaceId: string) {
  const refresh = useRefreshInvites(workspaceId);
  return useMutation({
    mutationFn: async (invitationId: string) => {
      unwrap(
        await apiClient.DELETE("/v1/workspaces/{workspace_id}/invites/{invitation_id}", {
          params: { path: { workspace_id: workspaceId, invitation_id: invitationId } },
        }),
      );
    },
    onSuccess: refresh,
  });
}

/** `POST /v1/workspaces/{id}/invites/{invitation_id}/resend`: new link, new validity window. */
export function useResendInvite(workspaceId: string) {
  const refresh = useRefreshInvites(workspaceId);
  return useMutation({
    mutationFn: async (invitationId: string) =>
      unwrap(
        await apiClient.POST("/v1/workspaces/{workspace_id}/invites/{invitation_id}/resend", {
          params: { path: { workspace_id: workspaceId, invitation_id: invitationId } },
        }),
      ),
    onSuccess: refresh,
  });
}
