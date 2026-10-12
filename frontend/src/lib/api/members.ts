import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { type Me, meQueryKey, type Role } from "./auth";
import { apiClient, unwrap } from "./client";
import type { components } from "./schema.gen";

export type Member = components["schemas"]["MemberOut"];

export function membersQueryKey(workspaceId: string) {
  return ["api", "workspaces", workspaceId, "members"] as const;
}

/** Largest page `GET /v1/workspaces/{id}/members` accepts. */
const MEMBERS_PAGE_SIZE = 200;

/** Every member of the workspace, ordered by name, reading as many pages as needed. */
export async function fetchMembers(workspaceId: string, signal?: AbortSignal): Promise<Member[]> {
  const members: Member[] = [];
  for (;;) {
    const page = unwrap(
      await apiClient.GET("/v1/workspaces/{workspace_id}/members", {
        params: {
          path: { workspace_id: workspaceId },
          query: { limit: MEMBERS_PAGE_SIZE, offset: members.length },
        },
        signal,
      }),
    );
    members.push(...page.items);
    if (page.items.length === 0 || members.length >= page.total) {
      return members;
    }
  }
}

/**
 * Members of the workspace. The whole list is loaded because the API has no search: the screen
 * filters and pages it locally (a workspace has people, not thousands of rows).
 */
export function useMembers(workspaceId: string) {
  return useQuery({
    queryKey: membersQueryKey(workspaceId),
    queryFn: ({ signal }) => fetchMembers(workspaceId, signal),
  });
}

export interface MemberRoleChange {
  userId: string;
  role: Role;
}

/**
 * Refreshes the member list and, when the change touched the logged-in user, `me` too: their role
 * in the workspace (menu, guards) or the membership itself changed.
 */
function useAfterMemberChange(workspaceId: string) {
  const queryClient = useQueryClient();
  return async (userId: string) => {
    const me = queryClient.getQueryData<Me | null>(meQueryKey);
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: membersQueryKey(workspaceId) }),
      me?.user.id === userId
        ? queryClient.invalidateQueries({ queryKey: meQueryKey })
        : Promise.resolve(),
    ]);
  };
}

/** `PATCH /v1/workspaces/{id}/members/{user_id}`: 409 `last_owner`, 403 `role_not_allowed`. */
export function useChangeMemberRole(workspaceId: string) {
  const afterChange = useAfterMemberChange(workspaceId);
  return useMutation({
    mutationFn: async ({ userId, role }: MemberRoleChange) =>
      unwrap(
        await apiClient.PATCH("/v1/workspaces/{workspace_id}/members/{user_id}", {
          params: { path: { workspace_id: workspaceId, user_id: userId } },
          body: { role },
        }),
      ),
    onSuccess: (_member, { userId }) => afterChange(userId),
  });
}

/** `DELETE /v1/workspaces/{id}/members/{user_id}` (204); the account itself stays. */
export function useRemoveMember(workspaceId: string) {
  const afterChange = useAfterMemberChange(workspaceId);
  return useMutation({
    mutationFn: async (userId: string) => {
      unwrap(
        await apiClient.DELETE("/v1/workspaces/{workspace_id}/members/{user_id}", {
          params: { path: { workspace_id: workspaceId, user_id: userId } },
        }),
      );
    },
    onSuccess: (_data, userId) => afterChange(userId),
  });
}
