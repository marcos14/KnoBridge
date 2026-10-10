import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Outlet } from "react-router";

import { useCurrentWorkspace } from "@/hooks/use-current-workspace";
import { storeLastWorkspaceId } from "@/lib/lastWorkspace";

import { useWorkspaceSuspendedSignal } from "./useWorkspaceSuspended";

/**
 * Element of `/w/:workspaceId`, under `RequireWorkspaceRole` (so the user is a member). Remembers
 * the workspace as the last used one and replaces the page with the "suspended" state when the
 * workspace is suspended, known from `me` or from a 403 `workspace_suspended` of the API.
 */
export function WorkspaceLayout() {
  const { workspaceId } = useCurrentWorkspace();
  // A new key per workspace resets the suspension flag when the user switches.
  return <WorkspaceGate key={workspaceId} />;
}

function WorkspaceGate() {
  const { workspace } = useCurrentWorkspace();
  const suspendedByApi = useWorkspaceSuspendedSignal();
  const workspaceId = workspace?.id;

  useEffect(() => {
    if (workspaceId !== undefined) {
      storeLastWorkspaceId(workspaceId);
    }
  }, [workspaceId]);

  if (suspendedByApi || workspace?.status === "suspended") {
    return <WorkspaceSuspended />;
  }
  return <Outlet />;
}

function WorkspaceSuspended() {
  const { t } = useTranslation();

  return (
    <section role="alert" className="flex max-w-prose flex-col gap-2">
      <h1 className="text-xl font-semibold">{t("workspaceSuspended.title")}</h1>
      <p>{t("workspaceSuspended.description")}</p>
    </section>
  );
}
