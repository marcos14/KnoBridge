import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { DataTable, type DataTableColumn } from "@/components/DataTable";
import { FormAlert } from "@/components/FormAlert";
import { Button } from "@/components/ui/button";
import { translateApiError } from "@/i18n/apiErrors";
import { type Collection, useCollections, useDeleteCollection } from "@/lib/api/collections";
import { type Provider, useProviders } from "@/lib/api/providers";
import { clampOffset, pageOf } from "@/lib/pagination";

import { CollectionDialog } from "./CollectionDialog";
import { embeddingProviders } from "./collectionForm";

/** Rows per page of the collection table (paged in the browser). */
export const COLLECTIONS_PAGE_SIZE = 20;

type Feedback = { kind: "status" | "alert"; message: string } | null;

interface CollectionsListProps {
  workspaceId: string;
  /** Owner, admin or editor: create, edit and delete (viewers only read). */
  canManage: boolean;
}

export function CollectionsList({ workspaceId, canManage }: CollectionsListProps) {
  const { t } = useTranslation();
  const [requestedOffset, setRequestedOffset] = useState(0);
  const [feedback, setFeedback] = useState<Feedback>(null);
  const collections = useCollections(workspaceId);
  // Viewers may not list credentials (403); they see the model alone.
  const providers = useProviders(workspaceId, { enabled: canManage });
  const remove = useDeleteCollection(workspaceId);

  function onDelete(collection: Collection) {
    setFeedback(null);
    remove.mutate(collection.id, {
      onSuccess: () => {
        setFeedback({
          kind: "status",
          message: t("collections.deleted", { name: collection.name }),
        });
      },
      onError: (error) => {
        setFeedback({ kind: "alert", message: translateApiError(error, t) });
      },
    });
  }

  const title = (
    <div className="flex flex-col gap-1">
      <h1 className="text-xl font-semibold">{t("collections.title")}</h1>
      <p className="text-muted-foreground text-sm">{t("collections.description")}</p>
    </div>
  );

  if (collections.isPending || (canManage && providers.isPending)) {
    return (
      <>
        {title}
        <p role="status" className="text-sm">
          {t("collections.loading")}
        </p>
      </>
    );
  }
  if (collections.isError || providers.isError) {
    return (
      <>
        {title}
        <div className="flex flex-col items-start gap-3">
          <p role="alert" className="text-sm">
            {t("collections.loadFailed")}
          </p>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              void collections.refetch();
              if (canManage) {
                void providers.refetch();
              }
            }}
          >
            {t("collections.retry")}
          </Button>
        </div>
      </>
    );
  }

  const all = collections.data;
  const allProviders: readonly Provider[] = providers.data ?? [];
  const choices = embeddingProviders(allProviders);
  const providerNames = new Map(allProviders.map((item) => [item.id, item.name] as const));
  const offset = clampOffset(requestedOffset, COLLECTIONS_PAGE_SIZE, all.length);
  const showSaved = (key: "collections.created" | "collections.updated") => (saved: Collection) => {
    setFeedback({ kind: "status", message: t(key, { name: saved.name }) });
  };
  const columns: DataTableColumn<Collection>[] = [
    {
      key: "name",
      header: t("collections.columns.name"),
      cell: (item) => (
        <div className="flex flex-col">
          <Link
            to={`/w/${workspaceId}/collections/${item.id}`}
            className="font-medium underline-offset-4 hover:underline"
          >
            {item.name}
          </Link>
          {item.description !== "" && (
            <span className="text-muted-foreground text-sm">{item.description}</span>
          )}
        </div>
      ),
    },
    {
      key: "embedding",
      header: t("collections.columns.embedding"),
      cell: (item) =>
        [providerNames.get(item.provider_id), item.embedding_model]
          .filter((part) => part !== undefined)
          .join(" · "),
    },
    {
      key: "sources",
      header: t("collections.columns.sources"),
      className: "text-right",
      cell: (item) => item.source_count,
    },
    {
      key: "documents",
      header: t("collections.columns.documents"),
      className: "text-right",
      cell: (item) => item.document_count,
    },
    {
      key: "chunks",
      header: t("collections.columns.chunks"),
      className: "text-right",
      cell: (item) => item.chunk_count,
    },
  ];
  if (canManage) {
    columns.push({
      key: "actions",
      header: t("collections.columns.actions"),
      cell: (item) => (
        <div className="flex flex-wrap gap-2">
          <CollectionDialog
            workspaceId={workspaceId}
            collection={item}
            providers={choices}
            trigger={
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={remove.isPending}
                aria-label={t("collections.editLabel", { name: item.name })}
              >
                {t("collections.edit")}
              </Button>
            }
            onSaved={showSaved("collections.updated")}
          />
          <ConfirmDialog
            trigger={
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={remove.isPending}
                aria-label={t("collections.deleteLabel", { name: item.name })}
              >
                {t("collections.delete")}
              </Button>
            }
            title={t("collections.deleteTitle", { name: item.name })}
            description={t("collections.deleteDescription")}
            confirmLabel={t("collections.delete")}
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
        {canManage && choices.length > 0 && (
          <CollectionDialog
            workspaceId={workspaceId}
            providers={choices}
            trigger={<Button type="button">{t("collections.create")}</Button>}
            onSaved={showSaved("collections.created")}
          />
        )}
      </div>
      {canManage && choices.length === 0 && (
        <p className="text-sm">
          {t("collections.needProvider")}{" "}
          <Link to={`/w/${workspaceId}/providers`} className="underline underline-offset-4">
            {t("collections.goToProviders")}
          </Link>
        </p>
      )}
      {feedback?.kind === "alert" && (
        <FormAlert key={feedback.message} message={feedback.message} />
      )}
      {feedback?.kind === "status" && (
        <p role="status" className="text-sm">
          {feedback.message}
        </p>
      )}
      <DataTable
        label={t("collections.tableLabel")}
        columns={columns}
        rows={pageOf(all, offset, COLLECTIONS_PAGE_SIZE)}
        rowKey={(item) => item.id}
        emptyMessage={t("collections.empty")}
        pagination={{
          offset,
          limit: COLLECTIONS_PAGE_SIZE,
          total: all.length,
          onOffsetChange: setRequestedOffset,
        }}
      />
    </>
  );
}
