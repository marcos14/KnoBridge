import type { Me, Role, UserWorkspace } from "@/lib/api/auth";

/** Higher is more privileged; mirrors the backend `Role` order (owner > admin > editor > viewer). */
const ROLE_RANK: Record<Role, number> = {
  viewer: 0,
  editor: 1,
  admin: 2,
  owner: 3,
};

/** Every role, from most to least privileged. */
export const ROLES: readonly Role[] = ["owner", "admin", "editor", "viewer"];

/** Whether `role` grants at least the privileges of `minRole`. */
export function hasRole(role: Role, minRole: Role): boolean {
  return ROLE_RANK[role] >= ROLE_RANK[minRole];
}

/** Whether `role` manages people and settings of the workspace (owner or admin). */
export function canManageWorkspace(role: Role): boolean {
  return hasRole(role, "admin");
}

/**
 * Whether `actor` may grant `role` (invite or change a member to it) or manage a member holding
 * it: owners and admins only, and never a role above their own (the backend answers 403
 * `role_not_allowed`).
 */
export function canHandleRole(actor: Role, role: Role): boolean {
  return canManageWorkspace(actor) && hasRole(actor, role);
}

/** The membership of the current user in workspace `workspaceId`, if any. */
export function findWorkspace(
  me: Me | null | undefined,
  workspaceId: string | undefined,
): UserWorkspace | undefined {
  return me?.workspaces.find((workspace) => workspace.id === workspaceId);
}
