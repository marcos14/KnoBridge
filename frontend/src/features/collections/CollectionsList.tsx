import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { DataTable, type DataTableColumn } from "@/components/DataTable";
import { FormAlert } from "@/components/FormAlert";
import { ListToolbar, type ListToolbarFilter } from "@/components/ListToolbar";
import { Button } from "@/components/ui/button";
import { useListSearch } from "@/hooks/use-list-search";
import { useOffsetClamp } from "@/hooks/use-offset-clamp";
import { translateApiError } from "@/i18n/apiErrors";
import { type Collection, useCollectionPage, useDeleteCollection } from "@/lib/api/collections";
import { type Provider, useProviders } from "@/lib/api/providers";
import { hasListCriteria, type ListSearchSpec, sortLabelKey } from "@/lib/listSearch";
import { isUuid } from "@/lib/uuid";

import { CollectionDialog } from "./CollectionDialog";
import { embeddingProviders } from "./collectionForm";

/** Rows per page of the collection table (paged by the API). */
export const COLLECTIONS_PAGE_SIZE = 20;

const COLLECTION_SORTS = [
  "name",
  "-name",
  "-document_count",
  "-created_at",
  "-updated_at",
] as const;

/** Search, credential filter and sort of the list, in the URL. */
const COLLECTION_LIST: ListSearchSpec<"provider", (typeof COLLECTION_SORTS)[number]> = {
  filters: { provider: isUuid },
  sorts: COLLECTION_SORTS,
};

type Feedback = { kind: "status" | "alert"; message: string } | null;

interface CollectionsListProps {
  workspaceId: string;
  /** Owner, admin or editor: create, edit and delete (viewers only read). */
  canManage: boolean;
}

export function CollectionsList({ workspaceId, canManage }: CollectionsListProps) {
  const { t } = useTranslation();
  const [feedback, setFeedback] = useState<Feedback>(null);
  const { search, setQuery, setFilter, setSort, setOffset, clear } = useListSearch(COLLECTION_LIST);
  const collections = useCollectionPage(workspaceId, {
    query: search.query === "" ? undefined : search.query,
    provider_id: search.filters.provider,
    sort: search.sort,
    limit: COLLECTIONS_PAGE_SIZE,
    offset: search.offset,
  });
  useOffsetClamp(search.offset, COLLECTIONS_PAGE_SIZE, collections.data?.total, setOffset);
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
  if (collections.data === undefined || providers.isError) {
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

  const { items, total } = collections.data;
  const allProviders: readonly Provider[] = providers.data ?? [];
  const choices = embeddingProviders(allProviders);
  const providerNames = new Map(allProviders.map((item) => [item.id, item.name] as const));
  const criteria = hasListCriteria(search);
  // Viewers may not list credentials: they search and sort, without the credential filter.
  const filters: ListToolbarFilter[] = canManage
    ? [
        {
          key: "provider",
          label: t("collections.providerFilter"),
          allLabel: t("collections.allProviders"),
          value: search.filters.provider,
          options: choices.map((item) => ({ value: item.id, label: item.name })),
          onChange: (value) => {
            setFilter("provider", value);
          },
        },
      ]
    : [];
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
      <ListToolbar
        searchLabel={t("collections.listSearch")}
        searchPlaceholder={t("collections.listSearchPlaceholder")}
        query={search.query}
        onQueryChange={setQuery}
        filters={filters}
        sort={{
          value: search.sort,
          options: COLLECTION_SORTS.map((sort) => ({ value: sort, label: t(sortLabelKey(sort)) })),
          onChange: setSort,
        }}
        onClear={criteria ? clear : undefined}
      />
      <DataTable
        label={t("collections.tableLabel")}
        columns={columns}
        rows={items}
        rowKey={(item) => item.id}
        emptyMessage={
          criteria ? (
            t("listToolbar.noResults")
          ) : canManage && choices.length > 0 ? (
            <>
              {t("collections.emptyNext")}{" "}
              <Link to={`/w/${workspaceId}/sources`} className="underline underline-offset-4">
                {t("collections.goToSources")}
              </Link>
            </>
          ) : (
            t("collections.empty")
          )
        }
        busy={collections.isPlaceholderData}
        pagination={{
          offset: search.offset,
          limit: COLLECTIONS_PAGE_SIZE,
          total,
          onOffsetChange: setOffset,
        }}
      />
    </>
  );
}
