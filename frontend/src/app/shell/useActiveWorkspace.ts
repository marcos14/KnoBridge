import { useCurrentWorkspace } from "@/hooks/use-current-workspace";
import { useMe, type UserWorkspace } from "@/lib/api/auth";
import { pickWorkspace, readLastWorkspaceId } from "@/lib/lastWorkspace";

/**
 * Workspace the shell shows in the switcher and the menu. Inside `/w/:workspaceId` it is the one
 * in the URL (`undefined` if the user is not a member); elsewhere (`/account`, `/admin`) the last
 * used one, so the menu still leads back to it.
 */
export function useActiveWorkspace(): UserWorkspace | undefined {
  const { workspaceId, workspace } = useCurrentWorkspace();
  const { data: me } = useMe();

  if (workspaceId !== undefined) {
    return workspace;
  }
  return pickWorkspace(me?.workspaces ?? [], readLastWorkspaceId());
}
