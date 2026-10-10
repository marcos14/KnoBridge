import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { DataTable, type DataTableColumn } from "@/components/DataTable";
import { FormAlert } from "@/components/FormAlert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { translateApiError } from "@/i18n/apiErrors";
import type { Role } from "@/lib/api/auth";
import { type Member, useChangeMemberRole, useMembers, useRemoveMember } from "@/lib/api/members";
import { formatDateTime } from "@/lib/intl";
import { clampOffset, pageOf } from "@/lib/pagination";
import { canHandleRole } from "@/lib/roles";

import { filterMembers } from "./filterMembers";
import { RoleSelect } from "./RoleSelect";

/** Rows per page of the member table. */
export const MEMBERS_PAGE_SIZE = 20;

interface MembersListProps {
  workspaceId: string;
  /** The logged-in user and their role here: decide which rows can be managed. */
  currentUserId: string;
  actorRole: Role;
}

/**
 * Members of the workspace with search and paging in the browser. Owners and admins change roles
 * and remove members they may manage; everyone else reads the list.
 */
export function MembersList({ workspaceId, currentUserId, actorRole }: MembersListProps) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const searchId = useId();
  const [query, setQuery] = useState("");
  const [requestedOffset, setRequestedOffset] = useState(0);
  const [notice, setNotice] = useState<string | null>(null);
  const members = useMembers(workspaceId);
  const changeRole = useChangeMemberRole(workspaceId);
  const remove = useRemoveMember(workspaceId);
  const busy = changeRole.isPending || remove.isPending;

  const filtered = filterMembers(members.data ?? [], query);
  const offset = clampOffset(requestedOffset, MEMBERS_PAGE_SIZE, filtered.length);
  const canManage = (member: Member) => canHandleRole(actorRole, member.role);
  const anyManageable = members.data?.some(canManage) ?? false;

  function startAction() {
    setNotice(null);
    changeRole.reset();
    remove.reset();
  }

  function onRoleChange(member: Member, role: Role) {
    startAction();
    changeRole.mutate(
      { userId: member.user_id, role },
      {
        onSuccess: () => {
          setNotice(t("members.roleChanged", { name: member.name, role: t(`roles.${role}`) }));
        },
      },
    );
  }

  function onRemove(member: Member) {
    startAction();
    remove.mutate(member.user_id, {
      onSuccess: () => {
        if (member.user_id === currentUserId) {
          void navigate("/");
          return;
        }
        setNotice(t("members.removed", { name: member.name }));
      },
    });
  }

  const columns: DataTableColumn<Member>[] = [
    {
      key: "name",
      header: t("members.columns.name"),
      cell: (member) => (
        <span className="flex flex-wrap items-center gap-2 font-medium">
          {member.name}
          {member.user_id === currentUserId && (
            <Badge variant="secondary">{t("members.you")}</Badge>
          )}
        </span>
      ),
    },
    { key: "email", header: t("members.columns.email"), cell: (member) => member.email },
    {
      key: "role",
      header: t("members.columns.role"),
      cell: (member) =>
        canManage(member) ? (
          <RoleSelect
            value={member.role}
            actorRole={actorRole}
            label={t("members.roleLabel", { name: member.name })}
            disabled={busy}
            onChange={(role) => {
              onRoleChange(member, role);
            }}
          />
        ) : (
          t(`members.roleNames.${member.role}`)
        ),
    },
    {
      key: "joinedAt",
      header: t("members.columns.joinedAt"),
      cell: (member) => (
        <time dateTime={member.joined_at}>
          {formatDateTime(new Date(member.joined_at), i18n.language)}
        </time>
      ),
    },
  ];
  if (anyManageable) {
    columns.push({
      key: "actions",
      header: t("members.columns.actions"),
      cell: (member) =>
        canManage(member) && (
          <RemoveMember
            member={member}
            self={member.user_id === currentUserId}
            disabled={busy}
            onConfirm={onRemove}
          />
        ),
    });
  }

  if (members.isPending) {
    return (
      <p role="status" className="text-sm">
        {t("members.loading")}
      </p>
    );
  }
  if (members.isError) {
    return (
      <div className="flex flex-col items-start gap-3">
        <p role="alert" className="text-sm">
          {t("members.loadFailed")}
        </p>
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            void members.refetch();
          }}
        >
          {t("members.retry")}
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-2 sm:max-w-sm">
        <Label htmlFor={searchId}>{t("members.search")}</Label>
        <Input
          id={searchId}
          type="search"
          value={query}
          placeholder={t("members.searchPlaceholder")}
          onChange={(event) => {
            setQuery(event.target.value);
            setRequestedOffset(0);
          }}
        />
      </div>
      {changeRole.isError && <FormAlert message={translateApiError(changeRole.error, t)} />}
      {remove.isError && <FormAlert message={translateApiError(remove.error, t)} />}
      {notice !== null && (
        <p role="status" className="text-sm">
          {notice}
        </p>
      )}
      <DataTable
        label={t("members.tableLabel")}
        columns={columns}
        rows={pageOf(filtered, offset, MEMBERS_PAGE_SIZE)}
        rowKey={(member) => member.user_id}
        emptyMessage={t("members.empty")}
        pagination={{
          offset,
          limit: MEMBERS_PAGE_SIZE,
          total: filtered.length,
          onOffsetChange: setRequestedOffset,
        }}
      />
    </div>
  );
}

interface RemoveMemberProps {
  member: Member;
  /** The row of the logged-in user: removing it is leaving the workspace. */
  self: boolean;
  disabled: boolean;
  onConfirm: (member: Member) => void;
}

function RemoveMember({ member, self, disabled, onConfirm }: RemoveMemberProps) {
  const { t } = useTranslation();
  const label = self ? t("members.leave") : t("members.remove");

  return (
    <ConfirmDialog
      trigger={
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={disabled}
          aria-label={self ? undefined : t("members.removeLabel", { name: member.name })}
        >
          {label}
        </Button>
      }
      title={self ? t("members.leaveTitle") : t("members.removeTitle", { name: member.name })}
      description={
        self ? t("members.leaveDescription") : t("members.removeDescription", { name: member.name })
      }
      confirmLabel={label}
      onConfirm={() => {
        onConfirm(member);
      }}
    />
  );
}
