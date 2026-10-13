import { useTranslation } from "react-i18next";

import { DataTable, type DataTableColumn } from "@/components/DataTable";
import { formatCount, formatUsd } from "@/features/sources/format";
import type { InstanceDashboard } from "@/lib/api/adminDashboard";
import { formatDate } from "@/lib/intl";

type InstanceUsage = InstanceDashboard["usage"];
type WorkspaceUsage = InstanceUsage["by_workspace"][number];

/**
 * Usage of the whole instance in the dashboard period: estimated cost, tokens, answers, the
 * "partial cost" warning and the workspaces that cost the most.
 */
export function InstanceUsagePanel({ usage }: { usage: InstanceUsage }) {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;
  const count = (value: number) => formatCount(value, locale);
  // Half-open period `[start, end)`: the last day shown is the one just before `end`.
  const start = formatDate(new Date(usage.period_start), locale);
  const end = formatDate(new Date(Date.parse(usage.period_end) - 1), locale);
  const partial = usage.unpriced_runs > 0 || usage.unpriced_answers > 0;
  const totals = [
    {
      key: "cost",
      label: t("admin.dashboard.usage.cost"),
      value: formatUsd(usage.cost_usd, locale),
    },
    {
      key: "embeddingTokens",
      label: t("admin.dashboard.usage.embeddingTokens"),
      value: count(usage.embedding_tokens),
    },
    {
      key: "chatTokens",
      label: t("admin.dashboard.usage.chatTokens"),
      value: count(usage.chat_input_tokens + usage.chat_output_tokens),
    },
    { key: "answers", label: t("admin.dashboard.usage.answers"), value: count(usage.answers) },
  ];
  const columns: DataTableColumn<WorkspaceUsage>[] = [
    {
      key: "workspace",
      header: t("admin.dashboard.usage.columns.workspace"),
      cell: (row) => row.workspace_name,
    },
    {
      key: "cost",
      header: t("admin.dashboard.usage.columns.cost"),
      cell: (row) => formatUsd(row.cost_usd, locale),
      className: "text-right",
    },
    {
      key: "embeddingTokens",
      header: t("admin.dashboard.usage.columns.embeddingTokens"),
      cell: (row) => count(row.embedding_tokens),
      className: "text-right",
    },
    {
      key: "chatTokens",
      header: t("admin.dashboard.usage.columns.chatTokens"),
      cell: (row) => count(row.chat_input_tokens + row.chat_output_tokens),
      className: "text-right",
    },
  ];

  return (
    <section aria-labelledby="instance-usage-title" className="flex flex-col gap-3">
      <div className="flex flex-col gap-1">
        <h2 id="instance-usage-title" className="text-lg font-semibold">
          {t("admin.dashboard.usage.title")}
        </h2>
        <p className="text-muted-foreground text-sm">
          {t("admin.dashboard.usage.period", { start, end })}
        </p>
      </div>
      <dl className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {totals.map(({ key, label, value }) => (
          <div key={key} className="flex flex-col gap-1 rounded-md border p-3">
            <dt className="text-muted-foreground text-xs">{label}</dt>
            <dd className="text-2xl font-semibold tabular-nums">{value}</dd>
          </div>
        ))}
      </dl>
      {partial && (
        <p role="note" className="text-sm text-amber-700 dark:text-amber-400">
          {t("admin.dashboard.usage.partial", {
            runs: usage.unpriced_runs,
            answers: usage.unpriced_answers,
          })}
        </p>
      )}
      <h3 className="font-medium">{t("admin.dashboard.usage.byWorkspace")}</h3>
      <DataTable
        label={t("admin.dashboard.usage.byWorkspaceLabel")}
        columns={columns}
        rows={usage.by_workspace}
        rowKey={(row) => row.workspace_id}
        emptyMessage={t("admin.dashboard.usage.byWorkspaceEmpty")}
      />
    </section>
  );
}
