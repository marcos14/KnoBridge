import { useTranslation } from "react-i18next";

import { useCurrentWorkspace } from "@/hooks/use-current-workspace";
import { useWorkspaceAudit } from "@/lib/api/audit";
import { useMembers } from "@/lib/api/members";
import { toAuditQuery } from "@/lib/auditFilters";

import type { AuditActor } from "./actors";
import { AUDIT_PAGE_SIZE, AuditLog } from "./AuditLog";
import { useAuditSearch } from "./useAuditSearch";

/** `/w/:workspaceId/audit` (owner or admin): the workspace's audit trail. */
export function WorkspaceAuditPage() {
  const { t } = useTranslation();
  // The route sits under `RequireWorkspaceRole`, which already checked the membership and role.
  const { workspace } = useCurrentWorkspace();

  return (
    <div className="flex max-w-6xl flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold">{t("audit.title")}</h1>
        <p className="text-muted-foreground text-sm">{t("audit.description")}</p>
      </div>
      {workspace !== undefined && <WorkspaceAudit workspaceId={workspace.id} />}
    </div>
  );
}

function WorkspaceAudit({ workspaceId }: { workspaceId: string }) {
  const { search } = useAuditSearch();
  const events = useWorkspaceAudit(workspaceId, toAuditQuery(search, AUDIT_PAGE_SIZE));
  // Members name the authors and fill the actor filter; while they load, ids stand in.
  const members = useMembers(workspaceId);
  const actors: AuditActor[] = (members.data ?? []).map((member) => ({
    id: member.user_id,
    name: member.name,
  }));

  return <AuditLog events={events} actors={actors} />;
}
