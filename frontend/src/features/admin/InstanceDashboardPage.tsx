import { useTranslation } from "react-i18next";

import { DataTable, type DataTableColumn } from "@/components/DataTable";
import { formatCount } from "@/lib/numberFormat";
import { type InstanceDashboard, useInstanceDashboard } from "@/lib/api/adminDashboard";
import { formatDateTime } from "@/lib/intl";

import { InstanceHealthPanel } from "./InstanceHealthPanel";
import { InstanceUsagePanel } from "./InstanceUsagePanel";
import { ListState } from "./ListState";

type RecentFailure = InstanceDashboard["recent_failures"][number];

/**
 * `/admin` (superadmin): counts of the instance, recent failures, usage of the last 30 days and
 * the health of the services (loaded on its own, so the numbers do not wait for the checks).
 */
export function InstanceDashboardPage() {
  const { t } = useTranslation();
  const dashboard = useInstanceDashboard();

  return (
    <div className="flex max-w-6xl flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold">{t("admin.dashboard.title")}</h1>
        <p className="text-muted-foreground text-sm">{t("admin.dashboard.description")}</p>
      </div>
      <InstanceHealthPanel />
      <ListState
        query={dashboard}
        loading={t("admin.dashboard.loading")}
        failed={t("admin.dashboard.loadFailed")}
      >
        {(data) => (
          <>
            <InstanceCounts dashboard={data} />
            <RecentFailures failures={data.recent_failures} />
            <InstanceUsagePanel usage={data.usage} />
          </>
        )}
      </ListState>
    </div>
  );
}

function InstanceCounts({ dashboard }: { dashboard: InstanceDashboard }) {
  const { t, i18n } = useTranslation();
  const count = (value: number) => formatCount(value, i18n.language);
  const { workspaces, users } = dashboard;
  const cards = [
    {
      key: "workspaces",
      label: t("admin.dashboard.workspaces"),
      value: count(workspaces.total),
      detail: t("admin.dashboard.workspacesDetail", {
        active: count(workspaces.active),
        suspended: count(workspaces.suspended),
      }),
    },
    {
      key: "users",
      label: t("admin.dashboard.users"),
      value: count(users.total),
      detail: t("admin.dashboard.usersDetail", {
        active: count(users.active_30d),
        suspended: count(users.suspended),
        superadmins: count(users.superadmins),
      }),
    },
    {
      key: "failedRuns",
      label: t("admin.dashboard.failedRuns"),
      value: count(dashboard.failed_runs_7d),
    },
    {
      key: "failedAnswers",
      label: t("admin.dashboard.failedAnswers"),
      value: count(dashboard.failed_answers_7d),
    },
  ];

  return (
    <section aria-label={t("admin.dashboard.countsLabel")}>
      <dl className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {cards.map(({ key, label, value, detail }) => (
          <div key={key} className="flex flex-col gap-1 rounded-md border p-3">
            <dt className="text-muted-foreground text-xs">{label}</dt>
            <dd className="text-2xl font-semibold tabular-nums">{value}</dd>
            {detail !== undefined && <dd className="text-muted-foreground text-xs">{detail}</dd>}
          </div>
        ))}
      </dl>
    </section>
  );
}

function RecentFailures({ failures }: { failures: readonly RecentFailure[] }) {
  const { t, i18n } = useTranslation();
  const columns: DataTableColumn<RecentFailure>[] = [
    {
      key: "workspace",
      header: t("admin.dashboard.failures.columns.workspace"),
      cell: (failure) => failure.workspace_name,
    },
    {
      key: "source",
      header: t("admin.dashboard.failures.columns.source"),
      cell: (failure) => failure.source_name,
    },
    {
      key: "error",
      header: t("admin.dashboard.failures.columns.error"),
      cell: (failure) =>
        failure.error ?? (
          <span className="text-muted-foreground">{t("admin.dashboard.failures.noError")}</span>
        ),
    },
    {
      key: "finishedAt",
      header: t("admin.dashboard.failures.columns.finishedAt"),
      cell: (failure) =>
        failure.finished_at === null ? (
          "—"
        ) : (
          <time dateTime={failure.finished_at}>
            {formatDateTime(new Date(failure.finished_at), i18n.language)}
          </time>
        ),
    },
  ];

  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-lg font-semibold">{t("admin.dashboard.failures.title")}</h2>
      <DataTable
        label={t("admin.dashboard.failures.tableLabel")}
        columns={columns}
        rows={failures}
        rowKey={(failure) => failure.run_id}
        emptyMessage={t("admin.dashboard.failures.empty")}
      />
    </section>
  );
}
