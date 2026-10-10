import { Outlet } from "react-router";

import type { Role } from "@/lib/api/auth";

import { ForbiddenPage } from "./ForbiddenPage";
import { hasRole } from "./roles";
import { useCurrentWorkspace } from "./useCurrentWorkspace";

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
