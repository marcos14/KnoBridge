import { TriangleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { UsageReport, UsageTotals as Totals } from "@/lib/api/usage";
import { formatDate } from "@/lib/intl";
import { formatCount, formatUsd } from "@/lib/numberFormat";

interface UsageTotalsProps {
  report: UsageReport;
  busy: boolean;
}

interface Figure {
  key: keyof Totals;
  label: string;
}

/** A card of figures: a heading and its terms and values. */
function TotalsCard({
  title,
  figures,
  totals,
}: {
  title: string;
  figures: readonly Figure[];
  totals: Totals;
}) {
  const { i18n } = useTranslation();
  const isCost = (key: keyof Totals) => key.endsWith("cost_usd");

  return (
    <section aria-label={title} className="flex flex-col gap-2 rounded-md border p-3">
      <h2 className="text-sm font-medium">{title}</h2>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2">
        {figures.map(({ key, label }) => (
          <div key={key} className="flex flex-col gap-0.5">
            <dt className="text-muted-foreground text-xs">{label}</dt>
            <dd className="text-lg font-semibold tabular-nums">
              {isCost(key)
                ? formatUsd(totals[key], i18n.language)
                : formatCount(totals[key], i18n.language)}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

const EMBEDDING_FIGURES = [
  { key: "embedding_tokens", label: "usage.totals.embeddingTokens" },
  { key: "embedding_cost_usd", label: "usage.totals.embeddingCost" },
  { key: "runs", label: "usage.totals.runs" },
] as const;

const CHAT_FIGURES = [
  { key: "chat_input_tokens", label: "usage.totals.chatInputTokens" },
  { key: "chat_output_tokens", label: "usage.totals.chatOutputTokens" },
  { key: "chat_cost_usd", label: "usage.totals.chatCost" },
  { key: "answers", label: "usage.totals.answers" },
] as const;

/**
 * Totals of the whole period: the estimated cost, embeddings and chat, and a "partial cost"
 * warning when items had no price. The period comes back half-open, `[start, end)`, in UTC: the
 * last day shown is the one just before `end`.
 */
export function UsageTotals({ report, busy }: UsageTotalsProps) {
  const { t, i18n } = useTranslation();
  const { totals } = report;
  const start = formatDate(new Date(report.period_start), i18n.language, "UTC");
  const end = formatDate(new Date(Date.parse(report.period_end) - 1), i18n.language, "UTC");
  const partial = totals.unpriced_runs > 0 || totals.unpriced_answers > 0;

  return (
    <section aria-label={t("usage.totals.label")} aria-busy={busy} className="flex flex-col gap-3">
      <p className="text-muted-foreground text-sm">{t("usage.period", { start, end })}</p>
      <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,2fr)_minmax(0,2fr)]">
        <section
          aria-label={t("usage.totals.cost")}
          className="flex flex-col gap-1 rounded-md border p-3"
        >
          <h2 className="text-sm font-medium">{t("usage.totals.cost")}</h2>
          <p className="text-3xl font-semibold tabular-nums">
            {formatUsd(totals.cost_usd, i18n.language)}
          </p>
        </section>
        <TotalsCard
          title={t("usage.totals.embeddings")}
          figures={EMBEDDING_FIGURES.map(({ key, label }) => ({ key, label: t(label) }))}
          totals={totals}
        />
        <TotalsCard
          title={t("usage.totals.chat")}
          figures={CHAT_FIGURES.map(({ key, label }) => ({ key, label: t(label) }))}
          totals={totals}
        />
      </div>
      {partial && (
        <div
          role="note"
          aria-label={t("usage.partial.title")}
          className="flex gap-3 rounded-md border border-amber-500/50 bg-amber-500/10 p-3 text-sm"
        >
          <TriangleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          <div className="flex flex-col gap-1">
            <p className="font-medium">{t("usage.partial.title")}</p>
            <p>{t("usage.partial.description")}</p>
            <ul className="list-disc pl-5">
              {totals.unpriced_runs > 0 && (
                <li>{t("usage.partial.runs", { count: totals.unpriced_runs })}</li>
              )}
              {totals.unpriced_answers > 0 && (
                <li>{t("usage.partial.answers", { count: totals.unpriced_answers })}</li>
              )}
            </ul>
          </div>
        </div>
      )}
    </section>
  );
}
