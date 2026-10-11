import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { DataTable, type DataTableColumn } from "@/components/DataTable";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { translateApiError } from "@/i18n/apiErrors";
import { useCollections } from "@/lib/api/collections";
import { type Source, useDeleteSource, useSources } from "@/lib/api/sources";
import { clampOffset, pageOf } from "@/lib/pagination";

import { type Feedback, FeedbackMessage } from "./Feedback";
import { NextRun } from "./NextRun";
import { RelativeTime } from "./RelativeTime";
import { RunStatusBadge } from "./RunStatusBadge";
import { SourceDialog } from "./SourceDialog";
import { sourceLocation } from "./sourceForm";
import { SyncButton } from "./SyncButton";

/** Rows per page of the source table (paged in the browser). */
export const SOURCES_PAGE_SIZE = 20;

interface SourcesListProps {
  workspaceId: string;
  /** Owner, admin or editor: create, edit, delete and sync (viewers only read). */
  canManage: boolean;
}

export function SourcesList({ workspaceId, canManage }: SourcesListProps) {
  const { t } = useTranslation();
  const [requestedOffset, setRequestedOffset] = useState(0);
  const [feedback, setFeedback] = useState<Feedback>(null);
  const sources = useSources(workspaceId);
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

  const all = sources.data;
  const allCollections = collections.data;
  const collectionNames = new Map(allCollections.map((item) => [item.id, item.name] as const));
  const offset = clampOffset(requestedOffset, SOURCES_PAGE_SIZE, all.length);
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
      <DataTable
        label={t("sources.tableLabel")}
        columns={columns}
        rows={pageOf(all, offset, SOURCES_PAGE_SIZE)}
        rowKey={(item) => item.id}
        emptyMessage={t("sources.empty")}
        pagination={{
          offset,
          limit: SOURCES_PAGE_SIZE,
          total: all.length,
          onOffsetChange: setRequestedOffset,
        }}
      />
    </>
  );
}
