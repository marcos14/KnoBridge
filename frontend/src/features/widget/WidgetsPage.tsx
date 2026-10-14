import { useTranslation } from "react-i18next";
import { useMatch } from "react-router";

import { useCurrentWorkspace } from "@/hooks/use-current-workspace";

import { WidgetDetail } from "./WidgetDetail";
import { WidgetsList } from "./WidgetsList";
import { NEW_WIDGET_PATH } from "./widgetPaths";

/**
 * `/w/:workspaceId/widgets`, `/widgets/new` and `/widgets/:widgetId` (owner or admin): the
 * embeddable chat widgets of the workspace's products, created and configured here with a live
 * preview.
 */
export function WidgetsPage() {
  const { t } = useTranslation();
  // The route sits under `RequireWorkspaceRole`, which already checked the membership and role.
  const { workspace } = useCurrentWorkspace();
  // This page is the layout of the three routes; the child's param is read from the URL.
  const widgetId = useMatch("/w/:workspaceId/widgets/:widgetId")?.params.widgetId;

  if (workspace === undefined) {
    return <h1 className="text-xl font-semibold">{t("widgets.title")}</h1>;
  }
  return (
    <div className="flex max-w-6xl flex-col gap-6">
      {widgetId === undefined ? (
        <WidgetsList workspaceId={workspace.id} />
      ) : (
        <WidgetDetail
          key={widgetId}
          workspaceId={workspace.id}
          widgetId={widgetId === NEW_WIDGET_PATH ? undefined : widgetId}
        />
      )}
    </div>
  );
}
