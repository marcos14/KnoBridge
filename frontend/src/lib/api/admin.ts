import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { type Me, meQueryKey } from "./auth";
import { apiClient, unwrap } from "./client";
import type { components } from "./schema.gen";

export type AdminWorkspace = components["schemas"]["AdminWorkspaceOut"];
export type AdminUser = components["schemas"]["AdminUserOut"];
export type CreateWorkspaceInput = components["schemas"]["CreateWorkspaceRequest"];
export type CreatedWorkspace = components["schemas"]["CreatedWorkspaceOut"];
export type WorkspaceChange = components["schemas"]["UpdateWorkspaceRequest"];
export type UserChange = components["schemas"]["UpdateUserRequest"];

/** A search over an admin listing: `q` matches a substring, ignoring case (empty = everything). */
export interface AdminSearch {
  q: string;
  limit: number;
  offset: number;
}

export const adminWorkspacesQueryKey = ["api", "admin", "workspaces"] as const;
export const adminUsersQueryKey = ["api", "admin", "users"] as const;

function searchParams({ q, limit, offset }: AdminSearch) {
  const trimmed = q.trim();
  return { q: trimmed === "" ? undefined : trimmed, limit, offset };
}

/** One page of every workspace of the instance, by name; `q` searches name and slug. */
export function useAdminWorkspaces(search: AdminSearch) {
  return useQuery({
    queryKey: [...adminWorkspacesQueryKey, search],
    queryFn: async ({ signal }) =>
      unwrap(
        await apiClient.GET("/v1/admin/workspaces", {
          params: { query: searchParams(search) },
          signal,
        }),
      ),
    placeholderData: keepPreviousData,
  });
}

/** One page of every user of the instance, by name; `q` searches e-mail and name. */
export function useAdminUsers(search: AdminSearch) {
  return useQuery({
    queryKey: [...adminUsersQueryKey, search],
    queryFn: async ({ signal }) =>
      unwrap(
        await apiClient.GET("/v1/admin/users", { params: { query: searchParams(search) }, signal }),
      ),
    placeholderData: keepPreviousData,
  });
}

/**
 * `POST /v1/admin/workspaces`: creates the workspace and e-mails an owner invitation (409
 * `slug_taken`). The superadmin does not join it, so `me` stays as it is.
 */
export function useCreateWorkspace() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: CreateWorkspaceInput) =>
      unwrap(await apiClient.POST("/v1/admin/workspaces", { body })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: adminWorkspacesQueryKey }),
  });
}

export interface WorkspaceUpdate {
  workspaceId: string;
  change: WorkspaceChange;
}

/**
 * `PATCH /v1/admin/workspaces/{id}`: rename, suspend or reactivate. Refreshes the list and, when
 * the superadmin is a member of that workspace, `me` (switcher name, suspended state).
 */
export function useUpdateWorkspace() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ workspaceId, change }: WorkspaceUpdate) =>
      unwrap(
        await apiClient.PATCH("/v1/admin/workspaces/{workspace_id}", {
          params: { path: { workspace_id: workspaceId } },
          body: change,
        }),
      ),
    onSuccess: async (_workspace, { workspaceId }) => {
      const me = queryClient.getQueryData<Me | null>(meQueryKey);
      const member = me?.workspaces.some((workspace) => workspace.id === workspaceId) ?? false;
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: adminWorkspacesQueryKey }),
        member ? queryClient.invalidateQueries({ queryKey: meQueryKey }) : Promise.resolve(),
      ]);
    },
  });
}

export interface UserUpdate {
  userId: string;
  change: UserChange;
}

/**
 * `PATCH /v1/admin/users/{id}`: suspend (ends every session) or reactivate; grant or remove
 * superadmin (409 `last_superadmin`, `cannot_suspend_self`). Refreshes the list and, when the
 * change touched the logged-in user, `me` (the admin menu and guard read `is_superadmin`).
 */
export function useUpdateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ userId, change }: UserUpdate) =>
      unwrap(
        await apiClient.PATCH("/v1/admin/users/{user_id}", {
          params: { path: { user_id: userId } },
          body: change,
        }),
      ),
    onSuccess: async (_user, { userId }) => {
      const me = queryClient.getQueryData<Me | null>(meQueryKey);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: adminUsersQueryKey }),
        me?.user.id === userId
          ? queryClient.invalidateQueries({ queryKey: meQueryKey })
          : Promise.resolve(),
      ]);
    },
  });
}
