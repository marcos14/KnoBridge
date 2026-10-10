import { useTranslation } from "react-i18next";
import { useMatch } from "react-router";

import { useCurrentWorkspace } from "@/hooks/use-current-workspace";

import { ConversationsOverview } from "./ConversationsOverview";
import { WorkspaceConversationView } from "./WorkspaceConversationView";

/**
 * `/w/:workspaceId/conversations` and `/w/:workspaceId/conversations/:conversationId` (owner or
 * admin): how the chat is used, and any member's conversation read only.
 */
export function ConversationsPage() {
  const { t } = useTranslation();
  // The route sits under `RequireWorkspaceRole`, which already checked the membership and role.
  const { workspace } = useCurrentWorkspace();
  // This page is the layout of both routes; the child's param is read from the URL.
  const conversationId = useMatch("/w/:workspaceId/conversations/:conversationId")?.params
    .conversationId;

  return (
    <div className="flex max-w-6xl flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold">{t("conversations.title")}</h1>
        {conversationId === undefined && (
          <p className="text-muted-foreground text-sm">{t("conversations.description")}</p>
        )}
      </div>
      {workspace !== undefined &&
        (conversationId === undefined ? (
          <ConversationsOverview workspaceId={workspace.id} />
        ) : (
          <WorkspaceConversationView
            key={conversationId}
            workspaceId={workspace.id}
            conversationId={conversationId}
          />
        ))}
    </div>
  );
}
