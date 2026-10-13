import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useCurrentWorkspace } from "@/hooks/use-current-workspace";
import { useMe } from "@/lib/api/auth";
import { canManageWorkspace } from "@/lib/roles";

import { InviteDialog } from "./InviteDialog";
import { InvitesList } from "./InvitesList";
import { MemberLevelsList } from "./MemberLevelsList";
import { MembersList } from "./MembersList";

type MembersTab = "members" | "levels" | "invites";

/**
 * `/w/:workspaceId/members`. Every member reads the list; owners and admins also manage roles and
 * each member's maximum level per product, remove members, invite and handle pending invitations.
 */
export function MembersPage() {
  const { t } = useTranslation();
  // The route sits under `RequireWorkspaceRole`, which already loaded `me` and the membership.
  const { data: me } = useMe();
  const { workspace } = useCurrentWorkspace();
  const [tab, setTab] = useState<MembersTab>("members");
  const [invitedEmail, setInvitedEmail] = useState<string | null>(null);

  if (!me || workspace === undefined) {
    return null;
  }
  const manager = canManageWorkspace(workspace.role);
  const members = (
    <MembersList workspaceId={workspace.id} currentUserId={me.user.id} actorRole={workspace.role} />
  );

  return (
    <div className="flex max-w-5xl flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h1 className="text-xl font-semibold">{t("members.title")}</h1>
          <p className="text-muted-foreground text-sm">{t("members.description")}</p>
        </div>
        {manager && (
          <InviteDialog
            workspaceId={workspace.id}
            actorRole={workspace.role}
            onInvited={(invitation) => {
              setInvitedEmail(invitation.email);
              setTab("invites");
            }}
          />
        )}
      </div>
      {invitedEmail !== null && (
        <p role="status" className="text-sm">
          {t("members.invite.sent", { email: invitedEmail })}
        </p>
      )}
      {manager ? (
        <Tabs
          value={tab}
          onValueChange={(value) => {
            setTab(value as MembersTab);
          }}
        >
          <TabsList>
            <TabsTrigger value="members">{t("members.tabs.members")}</TabsTrigger>
            <TabsTrigger value="levels">{t("members.tabs.levels")}</TabsTrigger>
            <TabsTrigger value="invites">{t("members.tabs.invites")}</TabsTrigger>
          </TabsList>
          <TabsContent value="members">{members}</TabsContent>
          <TabsContent value="levels">
            <MemberLevelsList workspaceId={workspace.id} actorRole={workspace.role} />
          </TabsContent>
          <TabsContent value="invites">
            <InvitesList workspaceId={workspace.id} actorRole={workspace.role} />
          </TabsContent>
        </Tabs>
      ) : (
        members
      )}
    </div>
  );
}
