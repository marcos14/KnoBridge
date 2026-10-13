import { useState } from "react";
import { useTranslation } from "react-i18next";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { DataTable, type DataTableColumn } from "@/components/DataTable";
import { FormAlert } from "@/components/FormAlert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useClock } from "@/hooks/use-clock";
import { useCurrentWorkspace } from "@/hooks/use-current-workspace";
import { translateApiError } from "@/i18n/apiErrors";
import { type ApiKey, useApiKeys, useRevokeApiKey } from "@/lib/api/apiKeys";
import { type Product, useProducts } from "@/lib/api/products";
import { formatDateTime, formatRelativeTime } from "@/lib/intl";
import { clampOffset, pageOf } from "@/lib/pagination";

import { ApiKeyDialog } from "./ApiKeyDialog";
import { ApiKeyExamples } from "./ApiKeyExamples";

/** Rows per page of the key table (paged in the browser). */
export const API_KEYS_PAGE_SIZE = 20;

type Feedback = { kind: "status" | "alert"; message: string } | null;

/**
 * `/w/:workspaceId/api-keys` (owner or admin): the workspace's API keys with scope, creation, last
 * use and state. Create (the secret shows once), edit name and scope, revoke; examples of use.
 */
export function ApiKeysPage() {
  const { t } = useTranslation();
  // The route sits under `RequireWorkspaceRole`, which already checked the membership.
  const { workspace } = useCurrentWorkspace();

  return (
    <div className="flex max-w-6xl flex-col gap-6">
      {workspace !== undefined ? (
        <div key={workspace.id} className="flex flex-col gap-6">
          <ApiKeysList workspaceId={workspace.id} />
          <ApiKeyExamples workspaceId={workspace.id} />
        </div>
      ) : (
        <h1 className="text-xl font-semibold">{t("apiKeys.title")}</h1>
      )}
    </div>
  );
}

function LastUsed({ value }: { value: string | null }) {
  const { t, i18n } = useTranslation();
  const clock = useClock();
  if (value === null) {
    return <span className="text-muted-foreground">{t("apiKeys.neverUsed")}</span>;
  }
  const date = new Date(value);
  return (
    <time dateTime={value} title={formatDateTime(date, i18n.language)}>
      {formatRelativeTime(date, clock(), i18n.language)}
    </time>
  );
}

function Scope({ apiKey, assistants }: { apiKey: ApiKey; assistants: Product[] | undefined }) {
  const { t } = useTranslation();
  const ids = apiKey.product_ids;
  if (ids === null) {
    return <span>{t("apiKeys.scope.all")}</span>;
  }
  if (assistants === undefined) {
    return <span>{t("apiKeys.scope.count", { count: ids.length })}</span>;
  }
  // A deleted assistant leaves the scope without an error (`docs/specs/api-publica.md`).
  const names = assistants.filter(({ id }) => ids.includes(id)).map(({ name }) => name);
  if (names.length === 0) {
    return <span className="text-muted-foreground">{t("apiKeys.scope.none")}</span>;
  }
  return <span>{names.join(", ")}</span>;
}

function ApiKeysList({ workspaceId }: { workspaceId: string }) {
  const { t, i18n } = useTranslation();
  const [requestedOffset, setRequestedOffset] = useState(0);
  const [feedback, setFeedback] = useState<Feedback>(null);
  const apiKeys = useApiKeys(workspaceId);
  const assistants = useProducts(workspaceId);
  const revoke = useRevokeApiKey(workspaceId);

  const showStatus = (message: string) => {
    setFeedback({ kind: "status", message });
  };

  function onRevoke(apiKey: ApiKey) {
    setFeedback(null);
    revoke.mutate(apiKey.id, {
      onSuccess: () => {
        showStatus(t("apiKeys.revoked", { name: apiKey.name }));
      },
      onError: (error) => {
        setFeedback({ kind: "alert", message: translateApiError(error, t) });
      },
    });
  }

  const header = (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold">{t("apiKeys.title")}</h1>
        <p className="text-muted-foreground text-sm">{t("apiKeys.description")}</p>
      </div>
      <ApiKeyDialog
        workspaceId={workspaceId}
        trigger={<Button type="button">{t("apiKeys.create")}</Button>}
        onSaved={showStatus}
      />
    </div>
  );

  if (apiKeys.isPending) {
    return (
      <>
        {header}
        <p role="status" className="text-sm">
          {t("apiKeys.loading")}
        </p>
      </>
    );
  }
  if (apiKeys.isError) {
    return (
      <>
        {header}
        <div className="flex flex-col items-start gap-3">
          <p role="alert" className="text-sm">
            {t("apiKeys.loadFailed")}
          </p>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              void apiKeys.refetch();
            }}
          >
            {t("apiKeys.retry")}
          </Button>
        </div>
      </>
    );
  }

  const all = apiKeys.data;
  const offset = clampOffset(requestedOffset, API_KEYS_PAGE_SIZE, all.length);
  const columns: DataTableColumn<ApiKey>[] = [
    {
      key: "name",
      header: t("apiKeys.columns.name"),
      cell: (item) => (
        <div className="flex flex-col gap-0.5">
          <span className="font-medium">{item.name}</span>
          <code className="text-muted-foreground text-xs">{`kbk_${item.key_prefix}_…`}</code>
        </div>
      ),
    },
    {
      key: "scope",
      header: t("apiKeys.columns.scope"),
      cell: (item) => <Scope apiKey={item} assistants={assistants.data} />,
    },
    {
      key: "created",
      header: t("apiKeys.columns.created"),
      cell: (item) => (
        <div className="flex flex-col gap-0.5">
          <time dateTime={item.created_at}>
            {formatDateTime(new Date(item.created_at), i18n.language)}
          </time>
          {item.created_by_name !== null && (
            <span className="text-muted-foreground text-xs">
              {t("apiKeys.createdBy", { name: item.created_by_name })}
            </span>
          )}
        </div>
      ),
    },
    {
      key: "lastUsed",
      header: t("apiKeys.columns.lastUsed"),
      cell: (item) => <LastUsed value={item.last_used_at} />,
    },
    {
      key: "status",
      header: t("apiKeys.columns.status"),
      cell: (item) =>
        item.revoked_at === null ? (
          <Badge>{t("apiKeys.status.active")}</Badge>
        ) : (
          <Badge variant="outline">{t("apiKeys.status.revoked")}</Badge>
        ),
    },
    {
      key: "actions",
      header: t("apiKeys.columns.actions"),
      cell: (item) =>
        item.revoked_at === null && (
          <div className="flex flex-wrap gap-2">
            <ApiKeyDialog
              workspaceId={workspaceId}
              apiKey={item}
              trigger={
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  aria-label={t("apiKeys.editLabel", { name: item.name })}
                >
                  {t("apiKeys.edit")}
                </Button>
              }
              onSaved={showStatus}
            />
            <ConfirmDialog
              trigger={
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={revoke.isPending}
                  aria-label={t("apiKeys.revokeLabel", { name: item.name })}
                >
                  {t("apiKeys.revoke")}
                </Button>
              }
              title={t("apiKeys.revokeTitle", { name: item.name })}
              description={t("apiKeys.revokeDescription")}
              confirmLabel={t("apiKeys.revoke")}
              onConfirm={() => {
                onRevoke(item);
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
        label={t("apiKeys.tableLabel")}
        columns={columns}
        rows={pageOf(all, offset, API_KEYS_PAGE_SIZE)}
        rowKey={(item) => item.id}
        emptyMessage={t("apiKeys.empty")}
        pagination={{
          offset,
          limit: API_KEYS_PAGE_SIZE,
          total: all.length,
          onOffsetChange: setRequestedOffset,
        }}
      />
    </>
  );
}
