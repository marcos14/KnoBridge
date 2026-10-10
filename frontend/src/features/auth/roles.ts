import type { Me, Role, UserWorkspace } from "@/lib/api/auth";

/** Higher is more privileged; mirrors the backend `Role` order (owner > admin > editor > viewer). */
const ROLE_RANK: Record<Role, number> = {
  viewer: 0,
  editor: 1,
  admin: 2,
  owner: 3,
};

/** Whether `role` grants at least the privileges of `minRole`. */
export function hasRole(role: Role, minRole: Role): boolean {
  return ROLE_RANK[role] >= ROLE_RANK[minRole];
}

/** The membership of the current user in workspace `workspaceId`, if any. */
export function findWorkspace(
  me: Me | null | undefined,
  workspaceId: string | undefined,
): UserWorkspace | undefined {
  return me?.workspaces.find((workspace) => workspace.id === workspaceId);
}
