import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { DataTable, type DataTableColumn } from "@/components/DataTable";
import { FormAlert } from "@/components/FormAlert";
import { Button } from "@/components/ui/button";
import { translateApiError } from "@/i18n/apiErrors";
import { type AdminWorkspace, useAdminWorkspaces, useUpdateWorkspace } from "@/lib/api/admin";
import { useEnterWorkspace } from "@/lib/api/workspaceAccess";
import { formatDateTime } from "@/lib/intl";

import { CreateWorkspaceDialog } from "./CreateWorkspaceDialog";
import { ListState } from "./ListState";
import { RenameWorkspaceDialog } from "./RenameWorkspaceDialog";
import { SearchForm } from "./SearchForm";
import { StatusBadge } from "./StatusBadge";

/** Rows per page of the admin tables (paged by the API). */
export const ADMIN_PAGE_SIZE = 20;

/**
 * `/admin/workspaces` (superadmin): every workspace; create, rename, suspend, reactivate and enter
 * (effective admin role in this session only).
 */
export function AdminWorkspacesPage() {
  const { t, i18n } = useTranslation();
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const [notice, setNotice] = useState<string | null>(null);
  const workspaces = useAdminWorkspaces({ q, limit: ADMIN_PAGE_SIZE, offset });
  const update = useUpdateWorkspace();
  const enter = useEnterWorkspace();
  const navigate = useNavigate();

  function startAction() {
    setNotice(null);
    update.reset();
    enter.reset();
  }

  function onRename(workspace: AdminWorkspace, name: string) {
    startAction();
    update.mutate(
      { workspaceId: workspace.id, change: { name } },
      {
        onSuccess: (updated) => {
          setNotice(t("admin.workspaces.rename.renamed", { name: updated.name }));
        },
      },
    );
  }

  function onToggleStatus(workspace: AdminWorkspace) {
    startAction();
    const suspend = workspace.status === "active";
    update.mutate(
      { workspaceId: workspace.id, change: { status: suspend ? "suspended" : "active" } },
      {
        onSuccess: () => {
          const key = suspend ? "admin.workspaces.suspended" : "admin.workspaces.reactivated";
          setNotice(t(key, { name: workspace.name }));
        },
      },
    );
  }

  function onEnter(workspace: AdminWorkspace) {
    startAction();
    enter.mutate(workspace.id, {
      onSuccess: () => {
        void navigate(`/w/${workspace.id}`);
      },
    });
  }

  const busy = update.isPending || enter.isPending;

  const columns: DataTableColumn<AdminWorkspace>[] = [
    {
      key: "name",
      header: t("admin.workspaces.columns.name"),
      cell: (workspace) => <span className="font-medium">{workspace.name}</span>,
    },
    {
      key: "slug",
      header: t("admin.workspaces.columns.slug"),
      cell: (workspace) => <code className="text-xs">{workspace.slug}</code>,
    },
    {
      key: "status",
      header: t("admin.workspaces.columns.status"),
      cell: (workspace) => <StatusBadge status={workspace.status} />,
    },
    {
      key: "members",
      header: t("admin.workspaces.columns.members"),
      cell: (workspace) => workspace.member_count,
      className: "text-right",
    },
    {
      key: "createdAt",
      header: t("admin.workspaces.columns.createdAt"),
      cell: (workspace) => (
        <time dateTime={workspace.created_at}>
          {formatDateTime(new Date(workspace.created_at), i18n.language)}
        </time>
      ),
    },
    {
      key: "actions",
      header: t("admin.workspaces.columns.actions"),
      cell: (workspace) => (
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            size="sm"
            disabled={busy || workspace.status === "suspended"}
            title={
              workspace.status === "suspended"
                ? t("admin.workspaces.enterSuspendedHint")
                : undefined
            }
            aria-label={t("admin.workspaces.enterLabel", { name: workspace.name })}
            onClick={() => {
              onEnter(workspace);
            }}
          >
            {t("admin.workspaces.enter")}
          </Button>
          <RenameWorkspaceDialog workspace={workspace} disabled={busy} onRename={onRename} />
          <StatusAction workspace={workspace} disabled={busy} onConfirm={onToggleStatus} />
        </div>
      ),
    },
  ];

  return (
    <div className="flex max-w-6xl flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h1 className="text-xl font-semibold">{t("admin.workspaces.title")}</h1>
          <p className="text-muted-foreground text-sm">{t("admin.workspaces.description")}</p>
        </div>
        <CreateWorkspaceDialog
          onCreated={({ workspace, owner_invitation }) => {
            startAction();
            setNotice(
              t("admin.workspaces.create.created", {
                name: workspace.name,
                email: owner_invitation.email,
              }),
            );
          }}
        />
      </div>
      <SearchForm
        placeholder={t("admin.workspaces.searchPlaceholder")}
        onSearch={(query) => {
          setQ(query);
          setOffset(0);
        }}
      />
      {update.isError && <FormAlert message={translateApiError(update.error, t)} />}
      {enter.isError && <FormAlert message={translateApiError(enter.error, t)} />}
      {notice !== null && (
        <p role="status" className="text-sm">
          {notice}
        </p>
      )}
      <ListState query={workspaces} loading={t("admin.workspaces.loading")}>
        {(page) => (
          <DataTable
            label={t("admin.workspaces.tableLabel")}
            columns={columns}
            rows={page.items}
            rowKey={(workspace) => workspace.id}
            emptyMessage={t("admin.workspaces.empty")}
            busy={workspaces.isPlaceholderData}
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

interface StatusActionProps {
  workspace: AdminWorkspace;
  disabled: boolean;
  onConfirm: (workspace: AdminWorkspace) => void;
}

/** "Suspend" (confirmed, destructive) or "Reactivate" for a workspace row. */
function StatusAction({ workspace, disabled, onConfirm }: StatusActionProps) {
  const { t } = useTranslation();
  const suspend = workspace.status === "active";
  const name = workspace.name;

  return (
    <ConfirmDialog
      trigger={
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={disabled}
          aria-label={
            suspend
              ? t("admin.workspaces.suspendLabel", { name })
              : t("admin.workspaces.reactivateLabel", { name })
          }
        >
          {suspend ? t("admin.workspaces.suspend") : t("admin.workspaces.reactivate")}
        </Button>
      }
      title={
        suspend
          ? t("admin.workspaces.suspendTitle", { name })
          : t("admin.workspaces.reactivateTitle", { name })
      }
      description={
        suspend
          ? t("admin.workspaces.suspendDescription")
          : t("admin.workspaces.reactivateDescription")
      }
      confirmLabel={suspend ? t("admin.workspaces.suspend") : t("admin.workspaces.reactivate")}
      destructive={suspend}
      onConfirm={() => {
        onConfirm(workspace);
      }}
    />
  );
}
