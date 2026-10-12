import type { UserWorkspace } from "./api/auth";
import { readStoredItem, writeStoredItem } from "./storage";

export const LAST_WORKSPACE_STORAGE_KEY = "knobridge-last-workspace";

export function readLastWorkspaceId(): string | undefined {
  return readStoredItem(LAST_WORKSPACE_STORAGE_KEY);
}

export function storeLastWorkspaceId(workspaceId: string): void {
  writeStoredItem(LAST_WORKSPACE_STORAGE_KEY, workspaceId);
}

/**
 * Workspace to open by default: the last one used while the user is still a member of it and it
 * is active, otherwise the first active one, otherwise the first one (which shows as suspended).
 */
export function pickWorkspace(
  workspaces: readonly UserWorkspace[],
  lastWorkspaceId: string | undefined,
): UserWorkspace | undefined {
  const active = workspaces.filter((workspace) => workspace.status === "active");
  return active.find((workspace) => workspace.id === lastWorkspaceId) ?? active[0] ?? workspaces[0];
}
