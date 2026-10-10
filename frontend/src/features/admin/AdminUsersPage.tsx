import { useState } from "react";
import { useTranslation } from "react-i18next";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { DataTable, type DataTableColumn } from "@/components/DataTable";
import { FormAlert } from "@/components/FormAlert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { translateApiError } from "@/i18n/apiErrors";
import { type AdminUser, type UserChange, useAdminUsers, useUpdateUser } from "@/lib/api/admin";
import { useMe } from "@/lib/api/auth";
import { formatDateTime } from "@/lib/intl";

import { ADMIN_PAGE_SIZE } from "./AdminWorkspacesPage";
import { ListState } from "./ListState";
import { SearchForm } from "./SearchForm";
import { StatusBadge } from "./StatusBadge";

/** What a row action does: its change, the confirmation texts and the notice after it. */
type UserAction = "suspend" | "reactivate" | "grant" | "revoke";

const CHANGES: Record<UserAction, UserChange> = {
  suspend: { status: "suspended" },
  reactivate: { status: "active" },
  grant: { is_superadmin: true },
  revoke: { is_superadmin: false },
};

const NOTICES = {
  suspend: "admin.users.suspended",
  reactivate: "admin.users.reactivated",
  grant: "admin.users.granted",
  revoke: "admin.users.revoked",
} as const;

/**
 * `/admin/users` (superadmin): every account; suspend or reactivate it, grant or remove
 * superadmin. Nobody suspends themselves (the backend answers `cannot_suspend_self`), so the
 * logged-in user's row has no "Suspend".
 */
export function AdminUsersPage() {
  const { t, i18n } = useTranslation();
  const { data: me } = useMe();
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const [notice, setNotice] = useState<string | null>(null);
  const users = useAdminUsers({ q, limit: ADMIN_PAGE_SIZE, offset });
  const update = useUpdateUser();
  const self = (user: AdminUser) => user.id === me?.user.id;

  function onAction(user: AdminUser, action: UserAction) {
    setNotice(null);
    update.reset();
    update.mutate(
      { userId: user.id, change: CHANGES[action] },
      {
        onSuccess: () => {
          setNotice(t(NOTICES[action], { name: user.name }));
        },
      },
    );
  }

  const columns: DataTableColumn<AdminUser>[] = [
    {
      key: "name",
      header: t("admin.users.columns.name"),
      cell: (user) => (
        <span className="flex flex-wrap items-center gap-2 font-medium">
          {user.name}
          {self(user) && <Badge variant="secondary">{t("admin.users.you")}</Badge>}
        </span>
      ),
    },
    {
      key: "email",
      header: t("admin.users.columns.email"),
      cell: (user) => (
        <span className="flex flex-col">
          {user.email}
          {user.email_verified_at === null && (
            <span className="text-muted-foreground text-xs">{t("admin.users.unverified")}</span>
          )}
        </span>
      ),
    },
    {
      key: "status",
      header: t("admin.users.columns.status"),
      cell: (user) => <StatusBadge status={user.status} />,
    },
    {
      key: "superadmin",
      header: t("admin.users.columns.superadmin"),
      cell: (user) => user.is_superadmin && <Badge>{t("admin.users.superadmin")}</Badge>,
    },
    {
      key: "createdAt",
      header: t("admin.users.columns.createdAt"),
      cell: (user) => (
        <time dateTime={user.created_at}>
          {formatDateTime(new Date(user.created_at), i18n.language)}
        </time>
      ),
    },
    {
      key: "actions",
      header: t("admin.users.columns.actions"),
      cell: (user) => {
        const statusAction = user.status === "active" ? "suspend" : "reactivate";
        return (
          <div className="flex flex-wrap gap-2">
            {!(self(user) && statusAction === "suspend") && (
              <ActionButton
                user={user}
                action={statusAction}
                disabled={update.isPending}
                onConfirm={onAction}
              />
            )}
            <ActionButton
              user={user}
              action={user.is_superadmin ? "revoke" : "grant"}
              disabled={update.isPending}
              onConfirm={onAction}
            />
          </div>
        );
      },
    },
  ];

  return (
    <div className="flex max-w-6xl flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold">{t("admin.users.title")}</h1>
        <p className="text-muted-foreground text-sm">{t("admin.users.description")}</p>
      </div>
      <SearchForm
        placeholder={t("admin.users.searchPlaceholder")}
        onSearch={(query) => {
          setQ(query);
          setOffset(0);
        }}
      />
      {update.isError && <FormAlert message={translateApiError(update.error, t)} />}
      {notice !== null && (
        <p role="status" className="text-sm">
          {notice}
        </p>
      )}
      <ListState query={users} loading={t("admin.users.loading")}>
        {(page) => (
          <DataTable
            label={t("admin.users.tableLabel")}
            columns={columns}
            rows={page.items}
            rowKey={(user) => user.id}
            emptyMessage={t("admin.users.empty")}
            busy={users.isPlaceholderData}
            pagination={{
              offset,
              limit: ADMIN_PAGE_SIZE,
              total: page.total,
              onOffsetChange: setOffset,
            }}
          />
        )}
      </ListState>
    </div>
  );
}

interface ActionButtonProps {
  user: AdminUser;
  action: UserAction;
  disabled: boolean;
  onConfirm: (user: AdminUser, action: UserAction) => void;
}

/** A row action behind a confirmation; suspending and removing superadmin are destructive. */
function ActionButton({ user, action, disabled, onConfirm }: ActionButtonProps) {
  const { t } = useTranslation();
  const name = user.name;

  return (
    <ConfirmDialog
      trigger={
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={disabled}
          aria-label={t(`admin.users.${action}Label`, { name })}
        >
          {t(`admin.users.${action}`)}
        </Button>
      }
      title={t(`admin.users.${action}Title`, { name })}
      description={t(`admin.users.${action}Description`, { name })}
      confirmLabel={t(`admin.users.${action}`)}
      destructive={action === "suspend" || action === "revoke"}
      onConfirm={() => {
        onConfirm(user, action);
      }}
    />
  );
}
