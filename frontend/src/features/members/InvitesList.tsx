import { useState } from "react";
import { useTranslation } from "react-i18next";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { DataTable, type DataTableColumn } from "@/components/DataTable";
import { FormAlert } from "@/components/FormAlert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useClock } from "@/hooks/use-clock";
import { translateApiError } from "@/i18n/apiErrors";
import type { Role } from "@/lib/api/auth";
import {
  type Invitation,
  useResendInvite,
  useRevokeInvite,
  useWorkspaceInvites,
} from "@/lib/api/invites";
import { formatDateTime, formatRelativeTime } from "@/lib/intl";
import { canHandleRole } from "@/lib/roles";

/** Rows per page of the invitation table (paged by the API). */
export const INVITES_PAGE_SIZE = 20;

interface InvitesListProps {
  workspaceId: string;
  actorRole: Role;
}

/** Pending invitations of the workspace: resend a new link or revoke it. */
export function InvitesList({ workspaceId, actorRole }: InvitesListProps) {
  const { t, i18n } = useTranslation();
  const clock = useClock();
  const [offset, setOffset] = useState(0);
  const [notice, setNotice] = useState<string | null>(null);
  const invites = useWorkspaceInvites(workspaceId, { limit: INVITES_PAGE_SIZE, offset });
  const resend = useResendInvite(workspaceId);
  const revoke = useRevokeInvite(workspaceId);
  const busy = resend.isPending || revoke.isPending;

  function startAction() {
    setNotice(null);
    resend.reset();
    revoke.reset();
  }

  function onResend(invitation: Invitation) {
    startAction();
    resend.mutate(invitation.id, {
      onSuccess: () => {
        setNotice(t("members.invites.resent", { email: invitation.email }));
      },
    });
  }

  function onRevoke(invitation: Invitation, lastOnPage: boolean) {
    startAction();
    revoke.mutate(invitation.id, {
      onSuccess: () => {
        setNotice(t("members.invites.revoked", { email: invitation.email }));
        // The page would come back empty: show the previous one.
        if (lastOnPage && offset > 0) {
          setOffset(offset - INVITES_PAGE_SIZE);
        }
      },
    });
  }

  if (invites.isPending) {
    return (
      <p role="status" className="text-sm">
        {t("members.invites.loading")}
      </p>
    );
  }
  if (invites.isError) {
    return (
      <div className="flex flex-col items-start gap-3">
        <p role="alert" className="text-sm">
          {t("members.invites.loadFailed")}
        </p>
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            void invites.refetch();
          }}
        >
          {t("members.retry")}
        </Button>
      </div>
    );
  }

  const rows = invites.data.items;
  const columns: DataTableColumn<Invitation>[] = [
    { key: "email", header: t("members.invites.columns.email"), cell: (item) => item.email },
    {
      key: "role",
      header: t("members.invites.columns.role"),
      cell: (item) => t(`members.roleNames.${item.role}`),
    },
    {
      key: "expiresAt",
      header: t("members.invites.columns.expiresAt"),
      cell: (item) => {
        const expiresAt = new Date(item.expires_at);
        return item.expired ? (
          <Badge variant="destructive">{t("members.invites.expired")}</Badge>
        ) : (
          <time dateTime={item.expires_at} title={formatDateTime(expiresAt, i18n.language)}>
            {t("members.invites.expiresAt", {
              when: formatRelativeTime(expiresAt, clock(), i18n.language),
            })}
          </time>
        );
      },
    },
    {
      key: "actions",
      header: t("members.invites.columns.actions"),
      cell: (item) =>
        canHandleRole(actorRole, item.role) && (
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={busy}
              aria-label={t("members.invites.resendLabel", { email: item.email })}
              onClick={() => {
                onResend(item);
              }}
            >
              {t("members.invites.resend")}
            </Button>
            <ConfirmDialog
              trigger={
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={busy}
                  aria-label={t("members.invites.revokeLabel", { email: item.email })}
                >
                  {t("members.invites.revoke")}
                </Button>
              }
              title={t("members.invites.revokeTitle", { email: item.email })}
              description={t("members.invites.revokeDescription")}
              confirmLabel={t("members.invites.revoke")}
              onConfirm={() => {
                onRevoke(item, rows.length === 1);
              }}
            />
          </div>
        ),
    },
  ];

  return (
    <div className="flex flex-col gap-4">
      {resend.isError && <FormAlert message={translateApiError(resend.error, t)} />}
      {revoke.isError && <FormAlert message={translateApiError(revoke.error, t)} />}
      {notice !== null && (
        <p role="status" className="text-sm">
          {notice}
        </p>
      )}
      <DataTable
        label={t("members.invites.tableLabel")}
        columns={columns}
        rows={rows}
        rowKey={(item) => item.id}
        emptyMessage={t("members.invites.empty")}
        busy={invites.isPlaceholderData}
        pagination={{
          offset,
          limit: INVITES_PAGE_SIZE,
          total: invites.data.total,
          onOffsetChange: setOffset,
        }}
      />
    </div>
  );
}
