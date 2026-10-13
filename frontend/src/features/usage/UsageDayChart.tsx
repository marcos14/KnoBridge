import { useTranslation } from "react-i18next";

import type { UsageRow } from "@/lib/api/usage";
import { formatUsd } from "@/lib/numberFormat";

import { formatUsageDay } from "./usageRows";

/** Height of the plot, in pixels. */
const PLOT_HEIGHT = 160;

/**
 * Bars of the estimated cost per day (`group_by=day`, one row per UTC day, in order). Plain CSS,
 * no chart library: one series, so no legend; each bar names its day and cost on hover and to
 * assistive technology, and the exact values are in the table below.
 */
export function UsageDayChart({ rows }: { rows: readonly UsageRow[] }) {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;
  const first = rows.at(0);
  const last = rows.at(-1);
  if (first === undefined || last === undefined) {
    return null;
  }
  const max = Math.max(...rows.map((row) => row.cost_usd));
  const start = formatUsageDay(first.key, locale);
  const end = formatUsageDay(last.key, locale);

  return (
    <figure className="flex flex-col gap-2 rounded-md border p-3">
      <figcaption className="text-sm font-medium">{t("usage.chart.title")}</figcaption>
      {max === 0 ? (
        <p className="text-muted-foreground text-sm">{t("usage.chart.empty")}</p>
      ) : (
        <>
          <p className="text-muted-foreground text-xs tabular-nums">{formatUsd(max, locale)}</p>
          <div
            role="list"
            aria-label={t("usage.chart.label", { start, end, max: formatUsd(max, locale) })}
            className="border-muted-foreground/40 flex items-end gap-0.5 border-b"
            style={{ height: PLOT_HEIGHT }}
          >
            {rows.map((row) => {
              const text = t("usage.chart.bar", {
                day: formatUsageDay(row.key, locale),
                cost: formatUsd(row.cost_usd, locale),
              });
              return (
                <div
                  key={row.key}
                  role="listitem"
                  aria-label={text}
                  title={text}
                  className="group flex h-full min-w-0 flex-1 items-end"
                >
                  <div
                    className="bg-primary group-hover:bg-primary/80 w-full rounded-t-[4px]"
                    style={{
                      height: `${String((row.cost_usd / max) * 100)}%`,
                      minHeight: row.cost_usd > 0 ? 1 : 0,
                    }}
                  />
                </div>
              );
            })}
          </div>
          <div className="text-muted-foreground flex justify-between text-xs">
            <span>{start}</span>
            <span>{end}</span>
          </div>
        </>
      )}
    </figure>
  );
}
