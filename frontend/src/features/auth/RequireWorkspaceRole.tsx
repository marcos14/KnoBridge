import { Outlet } from "react-router";

import { useCurrentWorkspace } from "@/hooks/use-current-workspace";
import type { Role } from "@/lib/api/auth";
import { hasRole } from "@/lib/roles";

import { ForbiddenPage } from "./ForbiddenPage";

interface RequireWorkspaceRoleProps {
  /** Least privileged role that may open the route. Defaults to any member. */
  minRole?: Role;
}

/**
 * Lets through members of the workspace in `/w/:workspaceId` whose role is at least `minRole`;
 * anyone else sees the 403 page. Must sit under `RequireAuth`, which loads the session first.
 */
export function RequireWorkspaceRole({ minRole = "viewer" }: RequireWorkspaceRoleProps) {
  const { workspace } = useCurrentWorkspace();

  if (workspace === undefined || !hasRole(workspace.role, minRole)) {
    return <ForbiddenPage />;
  }
  return <Outlet />;
}
