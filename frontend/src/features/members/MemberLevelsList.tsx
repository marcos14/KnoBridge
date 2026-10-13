import { useState } from "react";
import { useTranslation } from "react-i18next";

import { DataTable, type DataTableColumn } from "@/components/DataTable";
import { FormAlert } from "@/components/FormAlert";
import { ListToolbar } from "@/components/ListToolbar";
import { Button } from "@/components/ui/button";
import { useListSearch } from "@/hooks/use-list-search";
import { useOffsetClamp } from "@/hooks/use-offset-clamp";
import { translateApiError } from "@/i18n/apiErrors";
import type { Role } from "@/lib/api/auth";
import type { ResponseLevel } from "@/lib/api/levels";
import {
  type MemberLevels,
  type ProductRef,
  useMemberLevelsPage,
  useSetMemberLevel,
} from "@/lib/api/memberLevels";
import { hasListCriteria, sortLabelKey } from "@/lib/listSearch";
import { defaultMaxLevel, levelLabel } from "@/lib/responseLevels";
import { canHandleRole, ROLES } from "@/lib/roles";

import { DEFAULT_LEVEL, type LevelChoice, MemberLevelSelect } from "./MemberLevelSelect";
import { MEMBER_LIST, MEMBER_SORTS } from "./memberListSearch";
import { MEMBERS_PAGE_SIZE } from "./MembersList";

interface MemberLevelsListProps {
  workspaceId: string;
  /** Role of the logged-in owner or admin: members above it are read only (`role_not_allowed`). */
  actorRole: Role;
}

/**
 * The member × product table (owners and admins): each member's maximum level in each product,
 * the stored one or the default of the role, which is shown with the level it stands for. The
 * search, role filter, sort and page are the member list's, in the URL.
 */
export function MemberLevelsList({ workspaceId, actorRole }: MemberLevelsListProps) {
  const { t } = useTranslation();
  const [notice, setNotice] = useState<string | null>(null);
  const { search, setQuery, setFilter, setSort, setOffset, clear } = useListSearch(MEMBER_LIST);
  const page = useMemberLevelsPage(workspaceId, {
    query: search.query === "" ? undefined : search.query,
    role: ROLES.find((role) => role === search.filters.role),
    sort: search.sort,
    limit: MEMBERS_PAGE_SIZE,
    offset: search.offset,
  });
  useOffsetClamp(search.offset, MEMBERS_PAGE_SIZE, page.data?.total, setOffset);
  const setLevel = useSetMemberLevel(workspaceId);
  const criteria = hasListCriteria(search);
  const levelName = (level: ResponseLevel) => levelLabel(level, t);

  function onChange(member: MemberLevels, product: ProductRef, choice: LevelChoice) {
    setNotice(null);
    const maxLevel = choice === DEFAULT_LEVEL ? null : choice;
    setLevel.mutate(
      { userId: member.user_id, productId: product.id, maxLevel },
      {
        onSuccess: () => {
          setNotice(
            maxLevel === null
              ? t("members.levels.reset", { name: member.name, product: product.name })
              : t("members.levels.changed", {
                  name: member.name,
                  product: product.name,
                  level: levelName(maxLevel),
                }),
          );
        },
      },
    );
  }

  if (page.isPending) {
    return (
      <p role="status" className="text-sm">
        {t("members.levels.loading")}
      </p>
    );
  }
  if (page.data === undefined) {
    return (
      <div className="flex flex-col items-start gap-3">
        <p role="alert" className="text-sm">
          {t("members.levels.loadFailed")}
        </p>
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            void page.refetch();
          }}
        >
          {t("members.retry")}
        </Button>
      </div>
    );
  }

  const { products, items, total } = page.data;
  const columns: DataTableColumn<MemberLevels>[] = [
    {
      key: "name",
      header: t("members.columns.name"),
      cell: (member) => (
        <div className="flex flex-col">
          <span className="font-medium">{member.name}</span>
          <span className="text-muted-foreground text-xs">
            {t(`members.roleNames.${member.role}`)}
          </span>
        </div>
      ),
    },
    ...products.map((product, index): DataTableColumn<MemberLevels> => ({
      key: product.id,
      header: product.active ? product.name : t("members.levels.inactive", { name: product.name }),
      cell: (member) => {
        // The API answers one level per product, in the order of `products`.
        const level = member.levels[index];
        return (
          level !== undefined && (
            <MemberLevelSelect
              value={level.explicit ? level.max_level : DEFAULT_LEVEL}
              defaultLevel={defaultMaxLevel(member.role)}
              defaultLabel="members.levels.default"
              label={t("members.levels.cellLabel", { name: member.name, product: product.name })}
              disabled={setLevel.isPending || !canHandleRole(actorRole, member.role)}
              onChange={(choice) => {
                onChange(member, product, choice);
              }}
            />
          )
        );
      },
    })),
  ];

  return (
    <div className="flex flex-col gap-4">
      <p className="text-muted-foreground text-sm">{t("members.levels.description")}</p>
      {products.length === 0 ? (
        <p className="text-sm">{t("members.levels.noProducts")}</p>
      ) : (
        <>
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
                options: ROLES.map((role) => ({
                  value: role,
                  label: t(`members.roleNames.${role}`),
                })),
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
          {setLevel.isError && <FormAlert message={translateApiError(setLevel.error, t)} />}
          {notice !== null && (
            <p role="status" className="text-sm">
              {notice}
            </p>
          )}
          <DataTable
            label={t("members.levels.tableLabel")}
            columns={columns}
            rows={items}
            rowKey={(member) => member.user_id}
            emptyMessage={criteria ? t("listToolbar.noResults") : t("members.empty")}
            busy={page.isPlaceholderData}
            pagination={{
              offset: search.offset,
              limit: MEMBERS_PAGE_SIZE,
              total,
              onOffsetChange: setOffset,
            }}
          />
        </>
      )}
    </div>
  );
}
