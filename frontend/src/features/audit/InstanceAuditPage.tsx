import { useTranslation } from "react-i18next";

import { useAdminUsers } from "@/lib/api/admin";
import { useInstanceAudit } from "@/lib/api/audit";
import { toAuditQuery } from "@/lib/auditFilters";

import type { AuditActor } from "./actors";
import { AUDIT_PAGE_SIZE, AuditLog } from "./AuditLog";
import { useAuditSearch } from "./useAuditSearch";

/**
 * Users offered by the actor filter: the first page the API allows, by name. Authors beyond it
 * still show (by id) and stay filterable through a shared link.
 */
const ACTOR_USERS = { q: "", limit: 200, offset: 0 };

/** `/admin/audit` (superadmin): instance events (setup, logins, superadmin work). */
export function InstanceAuditPage() {
  const { t } = useTranslation();
  const { search } = useAuditSearch();
  const events = useInstanceAudit(toAuditQuery(search, AUDIT_PAGE_SIZE));
  const users = useAdminUsers(ACTOR_USERS);
  const actors: AuditActor[] = (users.data?.items ?? []).map((user) => ({
    id: user.id,
    name: user.name,
  }));

  return (
    <div className="flex max-w-6xl flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold">{t("audit.instanceTitle")}</h1>
        <p className="text-muted-foreground text-sm">{t("audit.instanceDescription")}</p>
      </div>
      <AuditLog events={events} actors={actors} />
    </div>
  );
}
