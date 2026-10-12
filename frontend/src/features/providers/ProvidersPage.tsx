import { useState } from "react";
import { useTranslation } from "react-i18next";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { DataTable, type DataTableColumn } from "@/components/DataTable";
import { FormAlert } from "@/components/FormAlert";
import { Button } from "@/components/ui/button";
import { useCurrentWorkspace } from "@/hooks/use-current-workspace";
import { translateApiError, translateApiErrorCode } from "@/i18n/apiErrors";
import {
  type Provider,
  useDeleteProvider,
  useProviders,
  useTestProvider,
} from "@/lib/api/providers";
import { clampOffset, pageOf } from "@/lib/pagination";

import { ProviderDialog } from "./ProviderDialog";

/** Rows per page of the provider table (paged in the browser). */
export const PROVIDERS_PAGE_SIZE = 20;

type Feedback = { kind: "status" | "alert"; message: string } | null;

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
  const [requestedOffset, setRequestedOffset] = useState(0);
  const [feedback, setFeedback] = useState<Feedback>(null);
  const providers = useProviders(workspaceId);
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
    test.mutate(provider.id, {
      // `error` is null exactly when `ok` is true.
      onSuccess: ({ error }) => {
        if (error === null) {
          showStatus(t("providers.testOk", { name: provider.name }));
          return;
        }
        showAlert(
          t("providers.testFailed", {
            name: provider.name,
            reason: translateApiErrorCode(error.code, t),
          }),
        );
      },
      onError: (error) => {
        showAlert(translateApiError(error, t));
      },
    });
  }

  function onDelete(provider: Provider) {
    setFeedback(null);
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
  if (providers.isError) {
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

  const all = providers.data;
  const offset = clampOffset(requestedOffset, PROVIDERS_PAGE_SIZE, all.length);
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
      ),
    },
  ];

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
      <DataTable
        label={t("providers.tableLabel")}
        columns={columns}
        rows={pageOf(all, offset, PROVIDERS_PAGE_SIZE)}
        rowKey={(item) => item.id}
        emptyMessage={t("providers.empty")}
        pagination={{
          offset,
          limit: PROVIDERS_PAGE_SIZE,
          total: all.length,
          onOffsetChange: setRequestedOffset,
        }}
      />
    </>
  );
}
