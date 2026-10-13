import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { DataTable, type DataTableColumn } from "@/components/DataTable";
import { ListToolbar } from "@/components/ListToolbar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useListSearch } from "@/hooks/use-list-search";
import { useOffsetClamp } from "@/hooks/use-offset-clamp";
import { translateApiError } from "@/i18n/apiErrors";
import { useCollections } from "@/lib/api/collections";
import { RESPONSE_LEVELS } from "@/lib/api/levels";
import { type Source, type SourceKind, useDeleteSource, useSourcePage } from "@/lib/api/sources";
import { levelLabel } from "@/lib/responseLevels";
import {
  booleanFilter,
  hasListCriteria,
  isBooleanFilter,
  type ListSearchSpec,
  oneOf,
  sortLabelKey,
} from "@/lib/listSearch";
import { isUuid } from "@/lib/uuid";

import { type Feedback, FeedbackMessage } from "./Feedback";
import { minLevelText } from "./format";
import { NextRun } from "./NextRun";
import { RelativeTime } from "./RelativeTime";
import { RunStatusBadge } from "./RunStatusBadge";
import { SourceDialog } from "./SourceDialog";
import { sourceLocation } from "./sourceForm";
import { SyncButton } from "./SyncButton";

/** Rows per page of the source table (paged by the API). */
export const SOURCES_PAGE_SIZE = 20;

const SOURCE_KINDS: readonly SourceKind[] = ["git", "folder", "runner", "tickets", "cards"];
const LAST_RUN_FILTERS = [
  "never",
  "queued",
  "running",
  "succeeded",
  "failed",
  "cancelled",
] as const;
const SOURCE_SORTS = ["name", "-name", "-last_run_at", "-created_at", "-updated_at"] as const;

/** Search, filters and sort of the list, in the URL. */
const SOURCE_LIST: ListSearchSpec<
  "kind" | "collection" | "active" | "lastRun" | "minLevel",
  (typeof SOURCE_SORTS)[number]
> = {
  filters: {
    kind: oneOf(SOURCE_KINDS),
    collection: isUuid,
    active: isBooleanFilter,
    lastRun: oneOf(LAST_RUN_FILTERS),
    minLevel: oneOf(RESPONSE_LEVELS),
  },
  sorts: SOURCE_SORTS,
};

interface SourcesListProps {
  workspaceId: string;
  /** Owner, admin or editor: create, edit, delete and sync (viewers only read). */
  canManage: boolean;
  /** Owner or admin: choose or change the minimum level of a source. */
  canManageLevel: boolean;
}

export function SourcesList({ workspaceId, canManage, canManageLevel }: SourcesListProps) {
  const { t } = useTranslation();
  const [feedback, setFeedback] = useState<Feedback>(null);
  const { search, setQuery, setFilter, setSort, setOffset, clear } = useListSearch(SOURCE_LIST);
  const { filters } = search;
  const sources = useSourcePage(workspaceId, {
    query: search.query === "" ? undefined : search.query,
    kind: SOURCE_KINDS.find((kind) => kind === filters.kind),
    collection_id: filters.collection,
    active: booleanFilter(filters.active),
    last_run_status: LAST_RUN_FILTERS.find((status) => status === filters.lastRun),
    min_level: RESPONSE_LEVELS.find((level) => level === filters.minLevel),
    sort: search.sort,
    limit: SOURCES_PAGE_SIZE,
    offset: search.offset,
  });
  useOffsetClamp(search.offset, SOURCES_PAGE_SIZE, sources.data?.total, setOffset);
  const collections = useCollections(workspaceId);
  const remove = useDeleteSource(workspaceId);

  function onDelete(source: Source) {
    setFeedback(null);
    remove.mutate(source.id, {
      onSuccess: () => {
        setFeedback({ kind: "status", message: t("sources.deleted", { name: source.name }) });
      },
      onError: (error) => {
        setFeedback({ kind: "alert", message: translateApiError(error, t) });
      },
    });
  }

  const title = (
    <div className="flex flex-col gap-1">
      <h1 className="text-xl font-semibold">{t("sources.title")}</h1>
      <p className="text-muted-foreground text-sm">{t("sources.description")}</p>
    </div>
  );

  if (sources.isPending || collections.isPending) {
    return (
      <>
        {title}
        <p role="status" className="text-sm">
          {t("sources.loading")}
        </p>
      </>
    );
  }
  // A failed poll keeps the list on screen; only a first load that fails replaces it.
  if (sources.data === undefined || collections.data === undefined) {
    return (
      <>
        {title}
        <div className="flex flex-col items-start gap-3">
          <p role="alert" className="text-sm">
            {t("sources.loadFailed")}
          </p>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              void sources.refetch();
              void collections.refetch();
            }}
          >
            {t("sources.retry")}
          </Button>
        </div>
      </>
    );
  }

  const { items, total } = sources.data;
  const allCollections = collections.data;
  const collectionNames = new Map(allCollections.map((item) => [item.id, item.name] as const));
  const criteria = hasListCriteria(search);
  const filter = (key: keyof typeof filters) => ({
    key,
    value: filters[key],
    onChange: (value: string | undefined) => {
      setFilter(key, value);
    },
  });
  const showSaved = (key: "sources.created" | "sources.updated") => (saved: Source) => {
    setFeedback({ kind: "status", message: t(key, { name: saved.name }) });
  };
  const columns: DataTableColumn<Source>[] = [
    {
      key: "name",
      header: t("sources.columns.name"),
      cell: (item) => (
        <div className="flex flex-col">
          <div className="flex flex-wrap items-center gap-2">
            <Link
              to={`/w/${workspaceId}/sources/${item.id}`}
              className="font-medium underline-offset-4 hover:underline"
            >
              {item.name}
            </Link>
            {!item.active && <Badge variant="outline">{t("sources.inactive")}</Badge>}
          </div>
          <span className="text-muted-foreground font-mono text-xs break-all">
            {sourceLocation(item)}
          </span>
        </div>
      ),
    },
    {
      key: "kind",
      header: t("sources.columns.kind"),
      cell: (item) => t(`sources.kinds.${item.kind}`),
    },
    {
      key: "collection",
      header: t("sources.columns.collection"),
      cell: (item) => collectionNames.get(item.collection_id),
    },
    {
      key: "minLevel",
      header: t("sources.columns.minLevel"),
      cell: (item) => minLevelText(item, t),
    },
    {
      key: "lastRun",
      header: t("sources.columns.lastRun"),
      cell: (item) =>
        item.last_run === null ? (
          <span className="text-muted-foreground text-sm">{t("sources.neverSynced")}</span>
        ) : (
          <div className="flex flex-col items-start gap-1">
            <RunStatusBadge status={item.last_run.status} />
            <span className="text-muted-foreground text-xs">
              <RelativeTime value={item.last_run.created_at} />
            </span>
          </div>
        ),
    },
    {
      key: "nextRun",
      header: t("sources.columns.nextRun"),
      cell: (item) => <NextRun source={item} />,
    },
  ];
  if (canManage) {
    columns.push({
      key: "actions",
      header: t("sources.columns.actions"),
      cell: (item) => (
        <div className="flex flex-wrap gap-2">
          <SyncButton workspaceId={workspaceId} source={item} size="sm" onFeedback={setFeedback} />
          <SourceDialog
            workspaceId={workspaceId}
            source={item}
            collections={allCollections}
            canManageLevel={canManageLevel}
            trigger={
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={remove.isPending}
                aria-label={t("sources.editLabel", { name: item.name })}
              >
                {t("sources.edit")}
              </Button>
            }
            onSaved={showSaved("sources.updated")}
          />
          <ConfirmDialog
            trigger={
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={remove.isPending}
                aria-label={t("sources.deleteLabel", { name: item.name })}
              >
                {t("sources.delete")}
              </Button>
            }
            title={t("sources.deleteTitle", { name: item.name })}
            description={t("sources.deleteDescription")}
            confirmLabel={t("sources.delete")}
            onConfirm={() => {
              onDelete(item);
            }}
          />
        </div>
      ),
    });
  }

  return (
    <>
      <div className="flex flex-wrap items-start justify-between gap-4">
        {title}
        {canManage && allCollections.length > 0 && (
          <SourceDialog
            workspaceId={workspaceId}
            collections={allCollections}
            canManageLevel={canManageLevel}
            trigger={<Button type="button">{t("sources.create")}</Button>}
            onSaved={showSaved("sources.created")}
          />
        )}
      </div>
      {canManage && allCollections.length === 0 && (
        <p className="text-sm">
          {t("sources.needCollection")}{" "}
          <Link to={`/w/${workspaceId}/collections`} className="underline underline-offset-4">
            {t("sources.goToCollections")}
          </Link>
        </p>
      )}
      <FeedbackMessage feedback={feedback} />
      <ListToolbar
        searchLabel={t("sources.search")}
        searchPlaceholder={t("sources.searchPlaceholder")}
        query={search.query}
        onQueryChange={setQuery}
        filters={[
          {
            ...filter("kind"),
            label: t("sources.columns.kind"),
            allLabel: t("sources.allKinds"),
            options: SOURCE_KINDS.map((kind) => ({
              value: kind,
              label: t(`sources.kinds.${kind}`),
            })),
          },
          {
            ...filter("collection"),
            label: t("sources.columns.collection"),
            allLabel: t("sources.allCollections"),
            options: allCollections.map((item) => ({ value: item.id, label: item.name })),
          },
          {
            ...filter("active"),
            label: t("listToolbar.status"),
            allLabel: t("listToolbar.allStatuses"),
            options: [
              { value: "true", label: t("sources.activeFilter") },
              { value: "false", label: t("sources.inactiveFilter") },
            ],
          },
          {
            ...filter("lastRun"),
            label: t("sources.columns.lastRun"),
            allLabel: t("sources.anyLastRun"),
            options: LAST_RUN_FILTERS.map((status) => ({
              value: status,
              label:
                status === "never" ? t("sources.neverSynced") : t(`sources.runStatus.${status}`),
            })),
          },
          {
            ...filter("minLevel"),
            label: t("sources.columns.minLevel"),
            allLabel: t("sources.allMinLevels"),
            options: RESPONSE_LEVELS.map((level) => ({
              value: level,
              label: levelLabel(level, t),
            })),
          },
        ]}
        sort={{
          value: search.sort,
          options: SOURCE_SORTS.map((sort) => ({ value: sort, label: t(sortLabelKey(sort)) })),
          onChange: setSort,
        }}
        onClear={criteria ? clear : undefined}
      />
      <DataTable
        label={t("sources.tableLabel")}
        columns={columns}
        rows={items}
        rowKey={(item) => item.id}
        emptyMessage={
          criteria
            ? t("listToolbar.noResults")
            : canManage && allCollections.length > 0
              ? t("sources.emptyNext")
              : t("sources.empty")
        }
        busy={sources.isPlaceholderData}
        pagination={{
          offset: search.offset,
          limit: SOURCES_PAGE_SIZE,
          total,
          onOffsetChange: setOffset,
        }}
      />
    </>
  );
}
