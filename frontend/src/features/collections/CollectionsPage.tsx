import { useTranslation } from "react-i18next";
import { useMatch } from "react-router";

import { useCurrentWorkspace } from "@/hooks/use-current-workspace";
import { hasRole } from "@/lib/roles";

import { CollectionDetail } from "./CollectionDetail";
import { CollectionsList } from "./CollectionsList";

/**
 * `/w/:workspaceId/collections` and `/w/:workspaceId/collections/:collectionId` (any member): the
 * workspace's collections and one collection with its sources and the search test. Owners,
 * admins and editors also create, edit and delete; viewers read and test the search.
 */
export function CollectionsPage() {
  const { t } = useTranslation();
  // The route sits under `RequireWorkspaceRole`, which already checked the membership.
  const { workspace } = useCurrentWorkspace();
  // This page is the layout of both routes; the child's param is read from the URL.
  const collectionId = useMatch("/w/:workspaceId/collections/:collectionId")?.params.collectionId;

  if (workspace === undefined) {
    return <h1 className="text-xl font-semibold">{t("collections.title")}</h1>;
  }
  const canManage = hasRole(workspace.role, "editor");
  return (
    <div className="flex max-w-5xl flex-col gap-6">
      {collectionId === undefined ? (
        <CollectionsList key={workspace.id} workspaceId={workspace.id} canManage={canManage} />
      ) : (
        <CollectionDetail
          key={`${workspace.id}/${collectionId}`}
          workspaceId={workspace.id}
          collectionId={collectionId}
          canManage={canManage}
        />
      )}
    </div>
  );
}
