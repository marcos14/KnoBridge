import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { DataTable, type DataTableColumn } from "@/components/DataTable";
import { FormAlert } from "@/components/FormAlert";
import { ListToolbar } from "@/components/ListToolbar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useCurrentWorkspace } from "@/hooks/use-current-workspace";
import { useListSearch } from "@/hooks/use-list-search";
import { useOffsetClamp } from "@/hooks/use-offset-clamp";
import { translateApiError } from "@/i18n/apiErrors";
import {
  type Product,
  useProductPage,
  useDeleteProduct,
  useDuplicateProduct,
} from "@/lib/api/products";
import { useCollections } from "@/lib/api/collections";
import { useProviders } from "@/lib/api/providers";
import {
  booleanFilter,
  hasListCriteria,
  isBooleanFilter,
  type ListSearchSpec,
  sortLabelKey,
} from "@/lib/listSearch";
import { canManageWorkspace } from "@/lib/roles";
import { isUuid } from "@/lib/uuid";

import { ProductDialog } from "./ProductDialog";

/** Rows per page of the product table (paged by the API). */
export const PRODUCTS_PAGE_SIZE = 20;

const PRODUCT_SORTS = ["name", "-name", "-created_at", "-updated_at"] as const;

/** Search, filters and sort of the list, in the URL. */
const PRODUCT_LIST: ListSearchSpec<"active" | "collection", (typeof PRODUCT_SORTS)[number]> = {
  filters: { active: isBooleanFilter, collection: isUuid },
  sorts: PRODUCT_SORTS,
};

type Feedback = { kind: "status" | "alert"; message: string } | null;

/**
 * `/w/:workspaceId/products` (owner, admin or editor): the workspace's products with their
 * status. Create, edit and delete (deleting also deletes the product's conversations).
 */
export function ProductsPage() {
  const { t } = useTranslation();
  // The route sits under `RequireWorkspaceRole`, which already checked the membership.
  const { workspace } = useCurrentWorkspace();

  return (
    <div className="flex max-w-5xl flex-col gap-6">
      {workspace !== undefined ? (
        <ProductsList
          key={workspace.id}
          workspaceId={workspace.id}
          canManageSecret={canManageWorkspace(workspace.role)}
        />
      ) : (
        <h1 className="text-xl font-semibold">{t("products.title")}</h1>
      )}
    </div>
  );
}

function ProductsList({
  workspaceId,
  canManageSecret,
}: {
  workspaceId: string;
  canManageSecret: boolean;
}) {
  const { t } = useTranslation();
  const [feedback, setFeedback] = useState<Feedback>(null);
  // The copy just made by "Duplicar", whose edit dialog opens at once.
  const [copy, setCopy] = useState<Product | null>(null);
  const { search, setQuery, setFilter, setSort, setOffset, clear } = useListSearch(PRODUCT_LIST);
  const { filters } = search;
  const products = useProductPage(workspaceId, {
    query: search.query === "" ? undefined : search.query,
    active: booleanFilter(filters.active),
    collection_id: filters.collection,
    sort: search.sort,
    limit: PRODUCTS_PAGE_SIZE,
    offset: search.offset,
  });
  useOffsetClamp(search.offset, PRODUCTS_PAGE_SIZE, products.data?.total, setOffset);
  const providers = useProviders(workspaceId);
  // Only names for the collection filter: while they load (or if they fail) it offers none.
  const collections = useCollections(workspaceId);
  const remove = useDeleteProduct(workspaceId);
  const duplicate = useDuplicateProduct(workspaceId);
  const busy = remove.isPending || duplicate.isPending;

  function onDuplicate(product: Product) {
    setFeedback(null);
    duplicate.mutate(product.id, {
      onSuccess: (created) => {
        setFeedback({
          kind: "status",
          message: t("products.duplicated", { name: created.name }),
        });
        setCopy(created);
      },
      onError: (error) => {
        setFeedback({ kind: "alert", message: translateApiError(error, t) });
      },
    });
  }

  function onDelete(product: Product) {
    setFeedback(null);
    remove.mutate(product.id, {
      onSuccess: () => {
        setFeedback({ kind: "status", message: t("products.deleted", { name: product.name }) });
      },
      onError: (error) => {
        setFeedback({ kind: "alert", message: translateApiError(error, t) });
      },
    });
  }

  const title = (
    <div className="flex flex-col gap-1">
      <h1 className="text-xl font-semibold">{t("products.title")}</h1>
      <p className="text-muted-foreground text-sm">{t("products.description")}</p>
    </div>
  );

  if (products.isPending || providers.isPending) {
    return (
      <>
        {title}
        <p role="status" className="text-sm">
          {t("products.loading")}
        </p>
      </>
    );
  }
  if (products.data === undefined || providers.isError) {
    return (
      <>
        {title}
        <div className="flex flex-col items-start gap-3">
          <p role="alert" className="text-sm">
            {t("products.loadFailed")}
          </p>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              void products.refetch();
              void providers.refetch();
            }}
          >
            {t("products.retry")}
          </Button>
        </div>
      </>
    );
  }

  const { items, total } = products.data;
  const providerList = providers.data;
  const criteria = hasListCriteria(search);
  const filter = (key: keyof typeof filters) => ({
    key,
    value: filters[key],
    onChange: (value: string | undefined) => {
      setFilter(key, value);
    },
  });
  const showSaved = (key: "products.created" | "products.updated") => (saved: Product) => {
    setFeedback({ kind: "status", message: t(key, { name: saved.name }) });
  };
  const columns: DataTableColumn<Product>[] = [
    {
      key: "name",
      header: t("products.columns.name"),
      cell: (item) => (
        <div className="flex flex-col">
          <span>{item.name}</span>
          {item.description !== "" && (
            <span className="text-muted-foreground text-sm">{item.description}</span>
          )}
        </div>
      ),
    },
    {
      key: "collections",
      header: t("products.columns.collections"),
      cell: (item) =>
        item.collection_ids.length > 0 ? (
          String(item.collection_ids.length)
        ) : (
          <span className="text-muted-foreground">{t("products.noCollections")}</span>
        ),
    },
    {
      key: "status",
      header: t("products.columns.status"),
      cell: (item) =>
        item.active ? (
          <Badge>{t("products.active")}</Badge>
        ) : (
          <Badge variant="secondary">{t("products.inactive")}</Badge>
        ),
    },
    {
      key: "actions",
      header: t("products.columns.actions"),
      cell: (item) => (
        <div className="flex flex-wrap gap-2">
          <ProductDialog
            workspaceId={workspaceId}
            product={item}
            canManageSecret={canManageSecret}
            trigger={
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={busy}
                aria-label={t("products.editLabel", { name: item.name })}
              >
                {t("products.edit")}
              </Button>
            }
            onSaved={showSaved("products.updated")}
          />
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={busy}
            aria-label={t("products.duplicateLabel", { name: item.name })}
            onClick={() => {
              onDuplicate(item);
            }}
          >
            {duplicate.isPending && duplicate.variables === item.id
              ? t("products.duplicating")
              : t("products.duplicate")}
          </Button>
          <ConfirmDialog
            trigger={
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={busy}
                aria-label={t("products.deleteLabel", { name: item.name })}
              >
                {t("products.delete")}
              </Button>
            }
            title={t("products.deleteTitle", { name: item.name })}
            description={t("products.deleteDescription")}
            confirmLabel={t("products.delete")}
            onConfirm={() => {
              onDelete(item);
            }}
          />
        </div>
      ),
    },
  ];

  return (
    <>
      <div className="flex flex-wrap items-start justify-between gap-4">
        {title}
        {providerList.length > 0 && (
          <ProductDialog
            workspaceId={workspaceId}
            canManageSecret={canManageSecret}
            trigger={<Button type="button">{t("products.create")}</Button>}
            onSaved={showSaved("products.created")}
          />
        )}
      </div>
      {providerList.length === 0 && (
        <p className="text-sm">
          {t("products.needProvider")}{" "}
          <Link to={`/w/${workspaceId}/providers`} className="underline underline-offset-4">
            {t("products.goToProviders")}
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
        searchLabel={t("products.search")}
        searchPlaceholder={t("products.searchPlaceholder")}
        query={search.query}
        onQueryChange={setQuery}
        filters={[
          {
            ...filter("active"),
            label: t("products.columns.status"),
            allLabel: t("listToolbar.allStatuses"),
            options: [
              { value: "true", label: t("listToolbar.activeOnly") },
              { value: "false", label: t("listToolbar.inactiveOnly") },
            ],
          },
          {
            ...filter("collection"),
            label: t("products.columns.collections"),
            allLabel: t("products.allCollections"),
            options: (collections.data ?? []).map((item) => ({ value: item.id, label: item.name })),
          },
        ]}
        sort={{
          value: search.sort,
          options: PRODUCT_SORTS.map((sort) => ({ value: sort, label: t(sortLabelKey(sort)) })),
          onChange: setSort,
        }}
        onClear={criteria ? clear : undefined}
      />
      <DataTable
        label={t("products.tableLabel")}
        columns={columns}
        rows={items}
        rowKey={(item) => item.id}
        emptyMessage={
          criteria ? (
            t("listToolbar.noResults")
          ) : providerList.length > 0 ? (
            <>
              {t("products.emptyNext")}{" "}
              <Link to={`/w/${workspaceId}/collections`} className="underline underline-offset-4">
                {t("products.goToCollections")}
              </Link>
            </>
          ) : (
            t("products.empty")
          )
        }
        busy={products.isPlaceholderData}
        pagination={{
          offset: search.offset,
          limit: PRODUCTS_PAGE_SIZE,
          total,
          onOffsetChange: setOffset,
        }}
      />
      {copy !== null && (
        <ProductDialog
          key={copy.id}
          workspaceId={workspaceId}
          product={copy}
          canManageSecret={canManageSecret}
          defaultOpen
          onClosed={() => {
            setCopy(null);
          }}
          onSaved={showSaved("products.updated")}
        />
      )}
    </>
  );
}
