import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { formatCount, formatUsd } from "@/lib/numberFormat";
import { useCurrentWorkspace } from "@/hooks/use-current-workspace";
import { useWorkspaceDashboard, type WorkspaceDashboard } from "@/lib/api/dashboard";
import { formatDate } from "@/lib/intl";

import { FirstSteps } from "./FirstSteps";

/**
 * `/w/:workspaceId`: the workspace home. Cards with this month's numbers (the cost only for owner
 * and admin, which is what the API sends) and the first-steps checklist.
 */
export function HomePage() {
  const { t } = useTranslation();
  const { workspaceId = "", workspace } = useCurrentWorkspace();
  const dashboard = useWorkspaceDashboard(workspaceId);

  return (
    <div className="flex max-w-6xl flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold">{t("home.title")}</h1>
        {workspace && (
          <p className="text-muted-foreground text-sm">
            {t("home.description", { name: workspace.name })}
          </p>
        )}
      </div>
      {dashboard.isPending ? (
        <p role="status" className="text-sm">
          {t("home.loading")}
        </p>
      ) : dashboard.isError ? (
        <div className="flex flex-col items-start gap-3">
          <p role="alert" className="text-sm">
            {t("home.loadFailed")}
          </p>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              void dashboard.refetch();
            }}
          >
            {t("home.retry")}
          </Button>
        </div>
      ) : (
        <>
          <FirstSteps
            checklist={dashboard.data.checklist}
            workspaceId={workspaceId}
            role={workspace?.role ?? "viewer"}
          />
          <DashboardCards dashboard={dashboard.data} />
        </>
      )}
    </div>
  );
}

interface Card {
  key: string;
  label: string;
  value: string;
  detail?: string;
}

function DashboardCards({ dashboard }: { dashboard: WorkspaceDashboard }) {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;
  const count = (value: number) => formatCount(value, locale);
  const cost = dashboard.cost_month;

  const cards: Card[] = [
    { key: "documents", label: t("home.cards.documents"), value: count(dashboard.documents) },
    {
      key: "sources",
      label: t("home.cards.sources"),
      value: t("home.cards.sourcesValue", {
        active: count(dashboard.sources.active),
        total: count(dashboard.sources.total),
      }),
    },
    { key: "failedRuns", label: t("home.cards.failedRuns"), value: count(dashboard.failed_runs) },
    {
      key: "conversations",
      label: t("home.cards.conversations"),
      value: count(dashboard.conversations_month),
    },
    {
      key: "feedbackUp",
      label: t("home.cards.feedbackUp"),
      value: count(dashboard.feedback_month.up),
    },
    {
      key: "feedbackDown",
      label: t("home.cards.feedbackDown"),
      value: count(dashboard.feedback_month.down),
    },
  ];
  if (cost !== null) {
    cards.push({
      key: "cost",
      label: t("home.cards.cost"),
      value: formatUsd(cost.cost_usd, locale),
      detail: t("home.cards.costDetail", {
        embedding: formatUsd(cost.embedding_cost_usd, locale),
        chat: formatUsd(cost.chat_cost_usd, locale),
      }),
    });
  }

  return (
    <section aria-label={t("home.cards.label")} className="flex flex-col gap-2">
      <p className="text-muted-foreground text-sm">
        {t("home.cards.monthSince", {
          date: formatDate(new Date(dashboard.month_start), locale, "UTC"),
        })}
      </p>
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {cards.map(({ key, label, value, detail }) => (
          <div key={key} className="flex flex-col gap-1 rounded-md border p-3">
            <dt className="text-muted-foreground text-xs">{label}</dt>
            <dd className="text-2xl font-semibold tabular-nums">{value}</dd>
            {detail !== undefined && <dd className="text-muted-foreground text-xs">{detail}</dd>}
          </div>
        ))}
      </dl>
      {cost?.partial === true && (
        <p role="note" className="text-sm text-amber-700 dark:text-amber-400">
          {t("home.cards.costPartial")}
        </p>
      )}
    </section>
  );
}
