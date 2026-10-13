import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { DataTable, type DataTableColumn } from "@/components/DataTable";
import { FormAlert } from "@/components/FormAlert";
import { ListToolbar } from "@/components/ListToolbar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useListSearch } from "@/hooks/use-list-search";
import { useOffsetClamp } from "@/hooks/use-offset-clamp";
import { translateApiError } from "@/i18n/apiErrors";
import type { Role } from "@/lib/api/auth";
import {
  type Member,
  useChangeMemberRole,
  useMemberPage,
  useRemoveMember,
} from "@/lib/api/members";
import { formatDateTime } from "@/lib/intl";
import { hasListCriteria, type ListSearchSpec, oneOf, sortLabelKey } from "@/lib/listSearch";
import { canHandleRole, ROLES } from "@/lib/roles";

import { RoleSelect } from "./RoleSelect";

/** Rows per page of the member table (paged by the API). */
export const MEMBERS_PAGE_SIZE = 20;

const MEMBER_SORTS = ["name", "-name", "email", "role", "-joined_at", "joined_at"] as const;

/** Search, role filter and sort of the list, in the URL. */
const MEMBER_LIST: ListSearchSpec<"role", (typeof MEMBER_SORTS)[number]> = {
  filters: { role: oneOf(ROLES) },
  sorts: MEMBER_SORTS,
};

interface MembersListProps {
  workspaceId: string;
  /** The logged-in user and their role here: decide which rows can be managed. */
  currentUserId: string;
  actorRole: Role;
}

/**
 * Members of the workspace with search, role filter, sort and paging by the API (state in the
 * URL). Owners and admins change roles and remove members they may manage; everyone else reads.
 */
export function MembersList({ workspaceId, currentUserId, actorRole }: MembersListProps) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const [notice, setNotice] = useState<string | null>(null);
  const { search, setQuery, setFilter, setSort, setOffset, clear } = useListSearch(MEMBER_LIST);
  const members = useMemberPage(workspaceId, {
    query: search.query === "" ? undefined : search.query,
    role: ROLES.find((role) => role === search.filters.role),
    sort: search.sort,
    limit: MEMBERS_PAGE_SIZE,
    offset: search.offset,
  });
  useOffsetClamp(search.offset, MEMBERS_PAGE_SIZE, members.data?.total, setOffset);
  const changeRole = useChangeMemberRole(workspaceId);
  const remove = useRemoveMember(workspaceId);
  const busy = changeRole.isPending || remove.isPending;
  const criteria = hasListCriteria(search);

  const canManage = (member: Member) => canHandleRole(actorRole, member.role);
  const anyManageable = members.data?.items.some(canManage) ?? false;

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
  if (members.data === undefined) {
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
      <ListToolbar
        searchLabel={t("members.search")}
        searchPlaceholder={t("members.searchPlaceholder")}
        query={search.query}
        onQueryChange={setQuery}
        filters={[
          {
            key: "role",
            label: t("members.columns.role"),
            allLabel: t("members.allRoles"),
            value: search.filters.role,
            options: ROLES.map((role) => ({ value: role, label: t(`members.roleNames.${role}`) })),
            onChange: (value) => {
              setFilter("role", value);
            },
          },
        ]}
        sort={{
          value: search.sort,
          options: MEMBER_SORTS.map((sort) => ({ value: sort, label: t(sortLabelKey(sort)) })),
          onChange: setSort,
        }}
        onClear={criteria ? clear : undefined}
      />
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
        rows={members.data.items}
        rowKey={(member) => member.user_id}
        emptyMessage={criteria ? t("listToolbar.noResults") : t("members.empty")}
        busy={members.isPlaceholderData}
        pagination={{
          offset: search.offset,
          limit: MEMBERS_PAGE_SIZE,
          total: members.data.total,
          onOffsetChange: setOffset,
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
