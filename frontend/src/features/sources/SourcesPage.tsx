import { useTranslation } from "react-i18next";
import { useMatch } from "react-router";

import { useCurrentWorkspace } from "@/hooks/use-current-workspace";
import { canManageWorkspace, hasRole } from "@/lib/roles";

import { SourceDetail } from "./SourceDetail";
import { SourcesList } from "./SourcesList";

/**
 * `/w/:workspaceId/sources` and `/w/:workspaceId/sources/:sourceId` (any member): the workspace's
 * sources and one source with its runs, their errors and its documents. Owners, admins and
 * editors also create, edit, delete, test and synchronize; viewers only read.
 */
export function SourcesPage() {
  const { t } = useTranslation();
  // The route sits under `RequireWorkspaceRole`, which already checked the membership.
  const { workspace } = useCurrentWorkspace();
  // This page is the layout of both routes; the child's param is read from the URL.
  const sourceId = useMatch("/w/:workspaceId/sources/:sourceId")?.params.sourceId;

  if (workspace === undefined) {
    return <h1 className="text-xl font-semibold">{t("sources.title")}</h1>;
  }
  const canManage = hasRole(workspace.role, "editor");
  return (
    <div className="flex max-w-6xl flex-col gap-6">
      {sourceId === undefined ? (
        <SourcesList key={workspace.id} workspaceId={workspace.id} canManage={canManage} />
      ) : (
        <SourceDetail
          key={`${workspace.id}/${sourceId}`}
          workspaceId={workspace.id}
          sourceId={sourceId}
          canManage={canManage}
          canManageTokens={canManageWorkspace(workspace.role)}
        />
      )}
    </div>
  );
}
