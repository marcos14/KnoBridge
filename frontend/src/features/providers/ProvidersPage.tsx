import { useState } from "react";
import { useTranslation } from "react-i18next";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { DataTable, type DataTableColumn } from "@/components/DataTable";
import { FormAlert } from "@/components/FormAlert";
import { ListToolbar } from "@/components/ListToolbar";
import { type TestOutcome, TestResult } from "@/components/TestResult";
import { Button } from "@/components/ui/button";
import { useCurrentWorkspace } from "@/hooks/use-current-workspace";
import { useListSearch } from "@/hooks/use-list-search";
import { useOffsetClamp } from "@/hooks/use-offset-clamp";
import { translateApiError, translateApiErrorCode } from "@/i18n/apiErrors";
import {
  type Provider,
  useDeleteProvider,
  useProviderPage,
  useTestProvider,
} from "@/lib/api/providers";
import { hasListCriteria, type ListSearchSpec, oneOf, sortLabelKey } from "@/lib/listSearch";

import { ProviderDialog } from "./ProviderDialog";
import { PROVIDER_KINDS } from "./providerForm";

/** Rows per page of the provider table (paged by the API). */
export const PROVIDERS_PAGE_SIZE = 20;

const PROVIDER_SORTS = ["name", "-name", "-created_at", "-updated_at"] as const;

/** Search, kind filter and sort of the list, in the URL. */
const PROVIDER_LIST: ListSearchSpec<"kind", (typeof PROVIDER_SORTS)[number]> = {
  filters: { kind: oneOf(PROVIDER_KINDS) },
  sorts: PROVIDER_SORTS,
};

/** The message on top; `quiet` when the same outcome is announced next to "Testar". */
type Feedback = { kind: "status" | "alert"; message: string; quiet?: boolean } | null;

/**
 * `/w/:workspaceId/providers` (owner, admin or editor): the workspace's LLM provider credentials.
 * Create, edit (new key optional), test the connection and delete; keys only appear masked.
 */
export function ProvidersPage() {
  const { t } = useTranslation();
  // The route sits under `RequireWorkspaceRole`, which already checked the membership.
  const { workspace } = useCurrentWorkspace();

  return (
    <div className="flex max-w-5xl flex-col gap-6">
      {workspace !== undefined ? (
        <ProvidersList key={workspace.id} workspaceId={workspace.id} />
      ) : (
        <h1 className="text-xl font-semibold">{t("providers.title")}</h1>
      )}
    </div>
  );
}

function ProvidersList({ workspaceId }: { workspaceId: string }) {
  const { t } = useTranslation();
  const [feedback, setFeedback] = useState<Feedback>(null);
  // The last "Testar" result, shown next to the button of its row.
  const [tested, setTested] = useState<{ id: string; outcome: TestOutcome } | null>(null);
  const { search, setQuery, setFilter, setSort, setOffset, clear } = useListSearch(PROVIDER_LIST);
  const providers = useProviderPage(workspaceId, {
    query: search.query === "" ? undefined : search.query,
    kind: PROVIDER_KINDS.find((kind) => kind === search.filters.kind),
    sort: search.sort,
    limit: PROVIDERS_PAGE_SIZE,
    offset: search.offset,
  });
  useOffsetClamp(search.offset, PROVIDERS_PAGE_SIZE, providers.data?.total, setOffset);
  const remove = useDeleteProvider(workspaceId);
  const test = useTestProvider(workspaceId);
  const busy = remove.isPending || test.isPending;

  const showStatus = (message: string) => {
    setFeedback({ kind: "status", message });
  };
  const showAlert = (message: string) => {
    setFeedback({ kind: "alert", message });
  };

  function onTest(provider: Provider) {
    setFeedback(null);
    setTested(null);
    const failed = (reason: string, message: string) => {
      setTested({ id: provider.id, outcome: { ok: false, message: reason } });
      setFeedback({ kind: "alert", message, quiet: true });
    };
    test.mutate(provider.id, {
      // `error` is null exactly when `ok` is true.
      onSuccess: ({ error }) => {
        if (error === null) {
          setTested({
            id: provider.id,
            outcome: { ok: true, message: t("providers.testOkShort") },
          });
          setFeedback({
            kind: "status",
            message: t("providers.testOk", { name: provider.name }),
            quiet: true,
          });
          return;
        }
        const reason = translateApiErrorCode(error.code, t);
        failed(reason, t("providers.testFailed", { name: provider.name, reason }));
      },
      onError: (error) => {
        const reason = translateApiError(error, t);
        failed(reason, reason);
      },
    });
  }

  function onDelete(provider: Provider) {
    setFeedback(null);
    setTested(null);
    remove.mutate(provider.id, {
      onSuccess: () => {
        showStatus(t("providers.deleted", { name: provider.name }));
      },
      onError: (error) => {
        showAlert(translateApiError(error, t));
      },
    });
  }

  const header = (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold">{t("providers.title")}</h1>
        <p className="text-muted-foreground text-sm">{t("providers.description")}</p>
      </div>
      <ProviderDialog
        workspaceId={workspaceId}
        trigger={<Button type="button">{t("providers.create")}</Button>}
        onSaved={(provider) => {
          showStatus(t("providers.created", { name: provider.name }));
        }}
      />
    </div>
  );

  const criteria = hasListCriteria(search);
  const toolbar = (
    <ListToolbar
      searchLabel={t("providers.search")}
      searchPlaceholder={t("providers.searchPlaceholder")}
      query={search.query}
      onQueryChange={setQuery}
      filters={[
        {
          key: "kind",
          label: t("providers.columns.kind"),
          allLabel: t("providers.allKinds"),
          value: search.filters.kind,
          options: PROVIDER_KINDS.map((kind) => ({
            value: kind,
            label: t(`providers.kinds.${kind}`),
          })),
          onChange: (value) => {
            setFilter("kind", value);
          },
        },
      ]}
      sort={{
        value: search.sort,
        options: PROVIDER_SORTS.map((sort) => ({ value: sort, label: t(sortLabelKey(sort)) })),
        onChange: setSort,
      }}
      onClear={criteria ? clear : undefined}
    />
  );

  if (providers.isPending) {
    return (
      <>
        {header}
        <p role="status" className="text-sm">
          {t("providers.loading")}
        </p>
      </>
    );
  }
  if (providers.data === undefined) {
    return (
      <>
        {header}
        <div className="flex flex-col items-start gap-3">
          <p role="alert" className="text-sm">
            {t("providers.loadFailed")}
          </p>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              void providers.refetch();
            }}
          >
            {t("providers.retry")}
          </Button>
        </div>
      </>
    );
  }

  const { items, total } = providers.data;
  const columns: DataTableColumn<Provider>[] = [
    { key: "name", header: t("providers.columns.name"), cell: (item) => item.name },
    {
      key: "kind",
      header: t("providers.columns.kind"),
      cell: (item) => t(`providers.kinds.${item.kind}`),
    },
    {
      key: "baseUrl",
      header: t("providers.columns.baseUrl"),
      cell: (item) =>
        item.base_url ?? (
          <span className="text-muted-foreground">{t("providers.defaultBaseUrl")}</span>
        ),
    },
    {
      key: "key",
      header: t("providers.columns.key"),
      cell: (item) => <code className="text-sm">{item.key_hint}</code>,
    },
    {
      key: "actions",
      header: t("providers.columns.actions"),
      cell: (item) => (
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={busy}
              aria-label={t("providers.testLabel", { name: item.name })}
              onClick={() => {
                onTest(item);
              }}
            >
              {test.isPending && test.variables === item.id
                ? t("providers.testing")
                : t("providers.test")}
            </Button>
            <ProviderDialog
              workspaceId={workspaceId}
              provider={item}
              trigger={
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={busy}
                  aria-label={t("providers.editLabel", { name: item.name })}
                >
                  {t("providers.edit")}
                </Button>
              }
              onSaved={(provider) => {
                showStatus(t("providers.updated", { name: provider.name }));
              }}
            />
            <ConfirmDialog
              trigger={
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={busy}
                  aria-label={t("providers.deleteLabel", { name: item.name })}
                >
                  {t("providers.delete")}
                </Button>
              }
              title={t("providers.deleteTitle", { name: item.name })}
              description={t("providers.deleteDescription")}
              confirmLabel={t("providers.delete")}
              onConfirm={() => {
                onDelete(item);
              }}
            />
          </div>
          {tested?.id === item.id && <TestResult outcome={tested.outcome} />}
        </div>
      ),
    },
  ];

  return (
    <>
      {header}
      {/* Keyed by message: a different failure mounts it again and moves the focus again. */}
      {feedback !== null && (
        <FormAlert
          key={feedback.message}
          message={feedback.message}
          variant={feedback.kind === "alert" ? "error" : "success"}
          quiet={feedback.quiet}
        />
      )}
      {toolbar}
      <DataTable
        label={t("providers.tableLabel")}
        columns={columns}
        rows={items}
        rowKey={(item) => item.id}
        emptyMessage={criteria ? t("listToolbar.noResults") : t("providers.empty")}
        busy={providers.isPlaceholderData}
        pagination={{
          offset: search.offset,
          limit: PROVIDERS_PAGE_SIZE,
          total,
          onOffsetChange: setOffset,
        }}
      />
    </>
  );
}
