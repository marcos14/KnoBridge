import { useParams } from "react-router";

import { useMe, type UserWorkspace } from "@/lib/api/auth";
import { findWorkspace } from "@/lib/roles";

export interface CurrentWorkspace {
  /** The `:workspaceId` of `/w/:workspaceId/...`, or `undefined` outside a workspace route. */
  workspaceId: string | undefined;
  /** The user's membership in that workspace, or `undefined` when there is none (or no session). */
  workspace: UserWorkspace | undefined;
}

/** Workspace selected by the URL. The path only selects it; access comes from the membership. */
export function useCurrentWorkspace(): CurrentWorkspace {
  const { workspaceId } = useParams();
  const { data: me } = useMe();
  return { workspaceId, workspace: findWorkspace(me, workspaceId) };
}
