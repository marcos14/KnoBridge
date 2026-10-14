import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { DataTable, type DataTableColumn } from "@/components/DataTable";
import { FormAlert } from "@/components/FormAlert";
import { ListToolbar } from "@/components/ListToolbar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useListSearch } from "@/hooks/use-list-search";
import { useOffsetClamp } from "@/hooks/use-offset-clamp";
import { translateApiError } from "@/i18n/apiErrors";
import { useProducts } from "@/lib/api/products";
import { type Widget, useDeleteWidget, useUpdateWidget, useWidgetPage } from "@/lib/api/widgets";
import {
  booleanFilter,
  hasListCriteria,
  isBooleanFilter,
  type ListSearchSpec,
} from "@/lib/listSearch";
import { isUuid } from "@/lib/uuid";

import { NEW_WIDGET_PATH, widgetPath } from "./widgetPaths";

/** Rows per page of the widget table (paged by the API). */
export const WIDGETS_PAGE_SIZE = 20;

/** Origins shown in the table before "+N". */
const ORIGINS_SHOWN = 2;

/** Search by name and the product and state filters, in the URL; the API orders by name. */
const WIDGET_LIST: ListSearchSpec<"product" | "active", "name"> = {
  filters: { product: isUuid, active: isBooleanFilter },
  sorts: ["name"],
};

type Feedback = { kind: "status" | "alert"; message: string } | null;

function Origins({ widget }: { widget: Widget }) {
  const { t } = useTranslation();
  const shown = widget.allowed_origins.slice(0, ORIGINS_SHOWN);
  const more = widget.allowed_origins.length - shown.length;
  return (
    <div className="flex flex-col gap-0.5 text-sm">
      {shown.map((origin) => (
        <code key={origin} className="break-all">
          {origin}
        </code>
      ))}
      {more > 0 && (
        <span className="text-muted-foreground text-xs">
          {t("widgets.moreOrigins", { count: more })}
        </span>
      )}
    </div>
  );
}

/** The widget list: search, filters, state, activate or deactivate and delete. */
export function WidgetsList({ workspaceId }: { workspaceId: string }) {
  const { t } = useTranslation();
  const [feedback, setFeedback] = useState<Feedback>(null);
  const { search, setQuery, setFilter, setOffset, clear } = useListSearch(WIDGET_LIST);
  const widgets = useWidgetPage(workspaceId, {
    query: search.query === "" ? undefined : search.query,
    product_id: search.filters.product,
    active: booleanFilter(search.filters.active),
    limit: WIDGETS_PAGE_SIZE,
    offset: search.offset,
  });
  useOffsetClamp(search.offset, WIDGETS_PAGE_SIZE, widgets.data?.total, setOffset);
  const products = useProducts(workspaceId);
  const update = useUpdateWidget(workspaceId);
  const remove = useDeleteWidget(workspaceId);
  const busy = update.isPending || remove.isPending;

  const showAlert = (error: Error) => {
    setFeedback({ kind: "alert", message: translateApiError(error, t) });
  };

  function onToggle(widget: Widget) {
    setFeedback(null);
    update.mutate(
      { widgetId: widget.id, changes: { active: !widget.active } },
      {
        onSuccess: (saved) => {
          setFeedback({
            kind: "status",
            message: t(saved.active ? "widgets.activated" : "widgets.deactivated", {
              name: saved.name,
            }),
          });
        },
        onError: showAlert,
      },
    );
  }

  function onDelete(widget: Widget) {
    setFeedback(null);
    remove.mutate(widget.id, {
      onSuccess: () => {
        setFeedback({ kind: "status", message: t("widgets.deleted", { name: widget.name }) });
      },
      onError: showAlert,
    });
  }

  const header = (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold">{t("widgets.title")}</h1>
        <p className="text-muted-foreground text-sm">{t("widgets.description")}</p>
      </div>
      <Button asChild>
        <Link to={widgetPath(workspaceId, NEW_WIDGET_PATH)}>{t("widgets.create")}</Link>
      </Button>
    </div>
  );

  if (widgets.isPending) {
    return (
      <>
        {header}
        <p role="status" className="text-sm">
          {t("widgets.loading")}
        </p>
      </>
    );
  }
  if (widgets.data === undefined) {
    return (
      <>
        {header}
        <div className="flex flex-col items-start gap-3">
          <p role="alert" className="text-sm">
            {t("widgets.loadFailed")}
          </p>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              void widgets.refetch();
            }}
          >
            {t("widgets.retry")}
          </Button>
        </div>
      </>
    );
  }

  const criteria = hasListCriteria(search);
  const productOptions = (products.data ?? []).map((product) => ({
    value: product.id,
    label: product.name,
  }));
  // A shared link may name a product that is not listed (deleted, or the list did not load).
  if (
    search.filters.product !== undefined &&
    !productOptions.some(({ value }) => value === search.filters.product)
  ) {
    productOptions.push({
      value: search.filters.product,
      label: t("widgets.unknownProduct", { id: search.filters.product }),
    });
  }
  const toolbar = (
    <ListToolbar
      searchLabel={t("widgets.search")}
      searchPlaceholder={t("widgets.searchPlaceholder")}
      query={search.query}
      onQueryChange={setQuery}
      filters={[
        {
          key: "product",
          label: t("widgets.columns.product"),
          allLabel: t("widgets.allProducts"),
          value: search.filters.product,
          options: productOptions,
          onChange: (value) => {
            setFilter("product", value);
          },
        },
        {
          key: "active",
          label: t("widgets.columns.status"),
          allLabel: t("listToolbar.allStatuses"),
          value: search.filters.active,
          options: [
            { value: "true", label: t("widgets.status.active") },
            { value: "false", label: t("widgets.status.inactive") },
          ],
          onChange: (value) => {
            setFilter("active", value);
          },
        },
      ]}
      onClear={criteria ? clear : undefined}
    />
  );

  const columns: DataTableColumn<Widget>[] = [
    {
      key: "name",
      header: t("widgets.columns.name"),
      cell: (item) => (
        <div className="flex flex-col gap-0.5">
          <Link
            to={widgetPath(workspaceId, item.id)}
            className="font-medium underline-offset-4 hover:underline"
          >
            {item.name}
          </Link>
          <code className="text-muted-foreground text-xs">{item.public_key}</code>
        </div>
      ),
    },
    { key: "product", header: t("widgets.columns.product"), cell: (item) => item.product_name },
    {
      key: "origins",
      header: t("widgets.columns.origins"),
      cell: (item) => <Origins widget={item} />,
    },
    {
      key: "mode",
      header: t("widgets.columns.mode"),
      cell: (item) => t(`widgets.modes.${item.mode}`),
    },
    {
      key: "status",
      header: t("widgets.columns.status"),
      cell: (item) =>
        item.active ? (
          <Badge>{t("widgets.status.active")}</Badge>
        ) : (
          <Badge variant="outline">{t("widgets.status.inactive")}</Badge>
        ),
    },
    {
      key: "actions",
      header: t("widgets.columns.actions"),
      cell: (item) => (
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline" size="sm">
            <Link
              to={widgetPath(workspaceId, item.id)}
              aria-label={t("widgets.configureLabel", { name: item.name })}
            >
              {t("widgets.configure")}
            </Link>
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={busy}
            aria-label={t(item.active ? "widgets.deactivateLabel" : "widgets.activateLabel", {
              name: item.name,
            })}
            onClick={() => {
              onToggle(item);
            }}
          >
            {item.active ? t("widgets.deactivate") : t("widgets.activate")}
          </Button>
          <ConfirmDialog
            trigger={
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={busy}
                aria-label={t("widgets.deleteLabel", { name: item.name })}
              >
                {t("widgets.delete")}
              </Button>
            }
            title={t("widgets.deleteTitle", { name: item.name })}
            description={t("widgets.deleteDescription")}
            confirmLabel={t("widgets.delete")}
            onConfirm={() => {
              onDelete(item);
            }}
          />
        </div>
      ),
    },
  ];

  const noProducts = products.data?.length === 0;
  const empty = criteria ? (
    t("listToolbar.noResults")
  ) : noProducts ? (
    <span>
      {t("widgets.emptyNoProducts")}{" "}
      <Link to={`/w/${workspaceId}/products`} className="underline underline-offset-4">
        {t("widgets.goToProducts")}
      </Link>
    </span>
  ) : (
    <span>
      {t("widgets.empty")}{" "}
      <Link to={widgetPath(workspaceId, NEW_WIDGET_PATH)} className="underline underline-offset-4">
        {t("widgets.createFirst")}
      </Link>
    </span>
  );

  return (
    <>
      {header}
      {/* Keyed by message: a different failure mounts it again and moves the focus again. */}
      {feedback?.kind === "alert" && (
        <FormAlert key={feedback.message} message={feedback.message} />
      )}
      {feedback?.kind === "status" && (
        <p role="status" className="text-sm">
          {feedback.message}
        </p>
      )}
      {toolbar}
      <DataTable
        label={t("widgets.tableLabel")}
        columns={columns}
        rows={widgets.data.items}
        rowKey={(item) => item.id}
        emptyMessage={empty}
        busy={widgets.isPlaceholderData}
        pagination={{
          offset: search.offset,
          limit: WIDGETS_PAGE_SIZE,
          total: widgets.data.total,
          onOffsetChange: setOffset,
        }}
      />
    </>
  );
}
