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
import { formatDateTime, formatRelativeTime } from "@/lib/intl";
import { type Runner, useDeleteRunner, useRunners, useUpdateRunner } from "@/lib/api/runners";
import { clampOffset, pageOf } from "@/lib/pagination";

import { CreateRunnerDialog } from "./CreateRunnerDialog";
import {
  executorState,
  isHarnessExecutor,
  runnerStatus,
  type RunnerStatus,
} from "@/lib/runnerStatus";

/** Rows per page of the runner table (paged in the browser). */
export const RUNNERS_PAGE_SIZE = 20;

type Feedback = { kind: "status" | "alert"; message: string } | null;

const STATUS_VARIANT: Record<RunnerStatus, "default" | "secondary" | "outline"> = {
  online: "default",
  offline: "secondary",
  revoked: "outline",
};

/**
 * `/w/:workspaceId/runners` (owner or admin): the workspace's local runners with presence, last
 * contact, version, executors and repositories. Create (the token shows once), revoke and delete.
 */
export function RunnersPage() {
  const { t } = useTranslation();
  // The route sits under `RequireWorkspaceRole`, which already checked the membership.
  const { workspace } = useCurrentWorkspace();

  return (
    <div className="flex max-w-6xl flex-col gap-6">
      {workspace !== undefined ? (
        <RunnersList key={workspace.id} workspaceId={workspace.id} />
      ) : (
        <h1 className="text-xl font-semibold">{t("runners.title")}</h1>
      )}
    </div>
  );
}

function LastSeen({ value }: { value: string | null }) {
  const { t, i18n } = useTranslation();
  const clock = useClock();
  if (value === null) {
    return <span className="text-muted-foreground">{t("runners.neverSeen")}</span>;
  }
  const date = new Date(value);
  return (
    <time dateTime={value} title={formatDateTime(date, i18n.language)}>
      {formatRelativeTime(date, clock(), i18n.language)}
    </time>
  );
}

function Executors({ runner }: { runner: Runner }) {
  const { t } = useTranslation();
  const { executors } = runner.capabilities;
  if (executors.length === 0) {
    return <span className="text-muted-foreground">{t("runners.noneReported")}</span>;
  }
  return (
    <ul className="flex flex-col gap-1">
      {executors.map((executor) => {
        const state = executorState(executor);
        // A newer runner may report an executor this panel does not know: shown as it came.
        const name = isHarnessExecutor(executor.name)
          ? t(`runners.executors.${executor.name}`)
          : executor.name;
        return (
          <li key={executor.name}>
            {[name, executor.version].filter(Boolean).join(" ")}
            {state !== "ready" && (
              <span className="text-muted-foreground">
                {" "}
                ({t(`runners.executorStates.${state}`)})
              </span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function Repositories({ runner }: { runner: Runner }) {
  const { t } = useTranslation();
  const { repositories } = runner.capabilities;
  if (repositories.length === 0) {
    return <span className="text-muted-foreground">{t("runners.noneReported")}</span>;
  }
  return (
    <ul className="flex flex-col gap-1">
      {repositories.map((repository) => (
        <li key={repository.name}>
          {[repository.name, repository.branch].filter(Boolean).join(" · ")}
          {repository.dirty && (
            <span className="text-muted-foreground"> · {t("runners.repositoryDirty")}</span>
          )}
        </li>
      ))}
    </ul>
  );
}

function RunnersList({ workspaceId }: { workspaceId: string }) {
  const { t } = useTranslation();
  const clock = useClock();
  const [requestedOffset, setRequestedOffset] = useState(0);
  const [feedback, setFeedback] = useState<Feedback>(null);
  const runners = useRunners(workspaceId);
  const update = useUpdateRunner(workspaceId);
  const remove = useDeleteRunner(workspaceId);
  const busy = update.isPending || remove.isPending;

  const showStatus = (message: string) => {
    setFeedback({ kind: "status", message });
  };
  const showAlert = (error: Error) => {
    setFeedback({ kind: "alert", message: translateApiError(error, t) });
  };

  function onRevoke(runner: Runner) {
    setFeedback(null);
    update.mutate(
      { runnerId: runner.id, changes: { revoked: true } },
      {
        onSuccess: () => {
          showStatus(t("runners.revoked", { name: runner.name }));
        },
        onError: showAlert,
      },
    );
  }

  function onDelete(runner: Runner) {
    setFeedback(null);
    remove.mutate(runner.id, {
      onSuccess: () => {
        showStatus(t("runners.deleted", { name: runner.name }));
      },
      onError: showAlert,
    });
  }

  const header = (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold">{t("runners.title")}</h1>
        <p className="text-muted-foreground text-sm">{t("runners.description")}</p>
      </div>
      <CreateRunnerDialog
        workspaceId={workspaceId}
        onCreated={() => {
          setFeedback(null);
        }}
      />
    </div>
  );

  if (runners.isPending) {
    return (
      <>
        {header}
        <p role="status" className="text-sm">
          {t("runners.loading")}
        </p>
      </>
    );
  }
  if (runners.isError) {
    return (
      <>
        {header}
        <div className="flex flex-col items-start gap-3">
          <p role="alert" className="text-sm">
            {t("runners.loadFailed")}
          </p>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              void runners.refetch();
            }}
          >
            {t("runners.retry")}
          </Button>
        </div>
      </>
    );
  }

  const all = runners.data;
  const offset = clampOffset(requestedOffset, RUNNERS_PAGE_SIZE, all.length);
  const now = clock();
  const columns: DataTableColumn<Runner>[] = [
    {
      key: "name",
      header: t("runners.columns.name"),
      cell: (item) => (
        <div className="flex flex-col gap-0.5">
          <span className="font-medium">{item.name}</span>
          <code className="text-muted-foreground text-xs">
            {t("runners.tokenPrefix", { token: `kbr_${item.token_prefix}_…` })}
          </code>
        </div>
      ),
    },
    {
      key: "status",
      header: t("runners.columns.status"),
      cell: (item) => {
        const status = runnerStatus(item, now);
        return <Badge variant={STATUS_VARIANT[status]}>{t(`runners.status.${status}`)}</Badge>;
      },
    },
    {
      key: "lastSeen",
      header: t("runners.columns.lastSeen"),
      cell: (item) => <LastSeen value={item.last_seen_at} />,
    },
    {
      key: "version",
      header: t("runners.columns.version"),
      cell: (item) => item.version ?? t("runners.noVersion"),
    },
    {
      key: "executors",
      header: t("runners.columns.executors"),
      cell: (item) => <Executors runner={item} />,
    },
    {
      key: "repositories",
      header: t("runners.columns.repositories"),
      cell: (item) => <Repositories runner={item} />,
    },
    {
      key: "actions",
      header: t("runners.columns.actions"),
      cell: (item) => (
        <div className="flex flex-wrap gap-2">
          {item.revoked_at === null && (
            <ConfirmDialog
              trigger={
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={busy}
                  aria-label={t("runners.revokeLabel", { name: item.name })}
                >
                  {t("runners.revoke")}
                </Button>
              }
              title={t("runners.revokeTitle", { name: item.name })}
              description={t("runners.revokeDescription")}
              confirmLabel={t("runners.revoke")}
              onConfirm={() => {
                onRevoke(item);
              }}
            />
          )}
          <ConfirmDialog
            trigger={
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={busy}
                aria-label={t("runners.deleteLabel", { name: item.name })}
              >
                {t("runners.delete")}
              </Button>
            }
            title={t("runners.deleteTitle", { name: item.name })}
            description={t("runners.deleteDescription")}
            confirmLabel={t("runners.delete")}
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
        label={t("runners.tableLabel")}
        columns={columns}
        rows={pageOf(all, offset, RUNNERS_PAGE_SIZE)}
        rowKey={(item) => item.id}
        emptyMessage={t("runners.empty")}
        pagination={{
          offset,
          limit: RUNNERS_PAGE_SIZE,
          total: all.length,
          onOffsetChange: setRequestedOffset,
        }}
      />
    </>
  );
}
