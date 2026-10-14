import { ArrowDown, ArrowUp, ArrowUpDown, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import {
  Table,
  TableBody,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { UsageGroup, UsageRow, UsageTotals } from "@/lib/api/usage";
import { parseChannel } from "@/lib/conversationFilters";
import { formatCount, formatUsd } from "@/lib/numberFormat";
import { levelLabel, parseLevel } from "@/lib/responseLevels";

import {
  COST_COLUMNS,
  formatUsageDay,
  isPartialRow,
  nextSort,
  sortUsageRows,
  type UsageColumn,
  usageColumns,
  type UsageSort,
  type UsageSortKey,
} from "./usageRows";

interface UsageTableProps {
  group: UsageGroup;
  /** Filtered by product or level: only the chat is counted, the embedding columns go. */
  chatOnly: boolean;
  rows: readonly UsageRow[];
  totals: UsageTotals;
  busy: boolean;
}

function SortIcon({ direction }: { direction: UsageSort["direction"] | undefined }) {
  const Icon = direction === undefined ? ArrowUpDown : direction === "asc" ? ArrowUp : ArrowDown;
  return <Icon aria-hidden="true" className="size-3.5" />;
}

/**
 * One row per group with the columns that apply to the grouping, sortable by any column (the
 * API's order until a header is clicked), and the period totals in the footer.
 */
export function UsageTable({ group, chatOnly, rows, totals, busy }: UsageTableProps) {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;
  const [sort, setSort] = useState<UsageSort | null>(null);
  const columns = usageColumns(group, chatOnly);
  const sorted = sortUsageRows(rows, sort);

  function value(column: UsageColumn, amount: number | null): string {
    if (amount === null) {
      return "—";
    }
    return COST_COLUMNS.has(column) ? formatUsd(amount, locale) : formatCount(amount, locale);
  }

  function label(row: UsageRow): string {
    if (group === "day") {
      return formatUsageDay(row.key, locale);
    }
    const channel = group === "channel" ? parseChannel(row.key) : undefined;
    if (channel !== undefined) {
      return t(`usage.channels.${channel}`);
    }
    const level = group === "level" ? parseLevel(row.key) : undefined;
    return level === undefined ? row.label : levelLabel(level, t);
  }

  function header(key: UsageSortKey, text: string, className?: string) {
    const direction = sort?.key === key ? sort.direction : undefined;
    return (
      <TableHead
        key={key}
        className={className}
        aria-sort={
          direction === undefined ? "none" : direction === "asc" ? "ascending" : "descending"
        }
      >
        <button
          type="button"
          className="inline-flex items-center gap-1 hover:underline"
          onClick={() => {
            setSort(nextSort(sort, key));
          }}
        >
          {text}
          <SortIcon direction={direction} />
        </button>
      </TableHead>
    );
  }

  return (
    <div className="rounded-md border">
      <Table
        aria-label={t("usage.table.label", { group: t(`usage.groups.${group}`) })}
        aria-busy={busy}
      >
        <TableHeader>
          <TableRow>
            {header("label", t(`usage.groups.${group}`))}
            {columns.map((column) =>
              header(column, t(`usage.table.columns.${column}`), "text-right"),
            )}
          </TableRow>
        </TableHeader>
        <TableBody>
          {sorted.length === 0 ? (
            <TableRow>
              <TableCell colSpan={columns.length + 1} className="text-muted-foreground py-6">
                {t("usage.table.empty")}
              </TableCell>
            </TableRow>
          ) : (
            sorted.map((row) => (
              <TableRow key={row.key}>
                <TableCell className="font-medium">{label(row)}</TableCell>
                {columns.map((column) => (
                  <TableCell key={column} className="text-right tabular-nums">
                    {column === "cost_usd" && isPartialRow(row) ? (
                      <span className="inline-flex items-center gap-1">
                        <TriangleAlert
                          role="img"
                          aria-label={t("usage.partial.row")}
                          className="size-3.5 text-amber-600"
                        />
                        {value(column, row[column])}
                      </span>
                    ) : (
                      value(column, row[column])
                    )}
                  </TableCell>
                ))}
              </TableRow>
            ))
          )}
        </TableBody>
        <TableFooter>
          <TableRow>
            <TableCell className="font-medium">{t("usage.table.total")}</TableCell>
            {columns.map((column) => (
              <TableCell key={column} className="text-right font-medium tabular-nums">
                {value(column, totals[column])}
              </TableCell>
            ))}
          </TableRow>
        </TableFooter>
      </Table>
    </div>
  );
}
