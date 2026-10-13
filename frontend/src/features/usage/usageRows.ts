import type { UsageGroup, UsageRow } from "@/lib/api/usage";
import { formatDate } from "@/lib/intl";

/** A `day` row key (`YYYY-MM-DD`, a UTC day) for reading. */
export function formatUsageDay(day: string, locale: string): string {
  return formatDate(new Date(`${day}T00:00:00Z`), locale, "UTC");
}

/** Numeric columns of a usage row, in reading order. */
export type UsageColumn =
  | "embedding_tokens"
  | "embedding_cost_usd"
  | "runs"
  | "chat_input_tokens"
  | "chat_output_tokens"
  | "chat_cost_usd"
  | "answers"
  | "cost_usd";

const EMBEDDING_COLUMNS = ["embedding_tokens", "embedding_cost_usd", "runs"] as const;
const CHAT_COLUMNS = [
  "chat_input_tokens",
  "chat_output_tokens",
  "chat_cost_usd",
  "answers",
] as const;

/** Columns holding US dollars (the rest are counts). */
export const COST_COLUMNS: ReadonlySet<UsageColumn> = new Set([
  "embedding_cost_usd",
  "chat_cost_usd",
  "cost_usd",
]);

/**
 * Columns that apply to a grouping (the API sends `null` for the others): embeddings for sources
 * and collections, chat for products, levels, channels and keys, both for models and days. A
 * report filtered by product or level (`chatOnly`) has no embeddings: only the chat columns.
 */
export function usageColumns(group: UsageGroup, chatOnly = false): UsageColumn[] {
  switch (group) {
    case "source":
    case "collection":
      return [...EMBEDDING_COLUMNS, "cost_usd"];
    case "product":
    case "level":
    case "channel":
    case "api_key":
      return [...CHAT_COLUMNS, "cost_usd"];
    case "model":
    case "day":
      return chatOnly
        ? [...CHAT_COLUMNS, "cost_usd"]
        : [...EMBEDDING_COLUMNS, ...CHAT_COLUMNS, "cost_usd"];
  }
}

export type UsageSortKey = "label" | UsageColumn;
export type SortDirection = "asc" | "desc";

export interface UsageSort {
  key: UsageSortKey;
  direction: SortDirection;
}

/** First direction of a column: names A→Z, numbers from the largest. */
export function firstDirection(key: UsageSortKey): SortDirection {
  return key === "label" ? "asc" : "desc";
}

/** The sort after clicking `key`: the same column flips, another starts in its first direction. */
export function nextSort(current: UsageSort | null, key: UsageSortKey): UsageSort {
  if (current?.key === key) {
    return { key, direction: current.direction === "asc" ? "desc" : "asc" };
  }
  return { key, direction: firstDirection(key) };
}

/** Whether a row has items left out of its cost because their model has no price. */
export function isPartialRow(row: UsageRow): boolean {
  return (row.unpriced_runs ?? 0) > 0 || (row.unpriced_answers ?? 0) > 0;
}

function compareLabels(a: UsageRow, b: UsageRow): number {
  return a.label.localeCompare(b.label);
}

/**
 * `rows` sorted by `sort` (a new array; `null` keeps the API's order). Missing values go last in
 * either direction; ties fall back to the label. `day` keys are `YYYY-MM-DD`, so the label order
 * is the calendar order.
 */
export function sortUsageRows(rows: readonly UsageRow[], sort: UsageSort | null): UsageRow[] {
  if (sort === null) {
    return [...rows];
  }
  const sign = sort.direction === "asc" ? 1 : -1;
  const { key } = sort;
  return [...rows].sort((a, b) => {
    if (key === "label") {
      return sign * compareLabels(a, b);
    }
    const left = a[key];
    const right = b[key];
    if (left === null || right === null) {
      return left === right ? compareLabels(a, b) : left === null ? 1 : -1;
    }
    return left === right ? compareLabels(a, b) : sign * (left - right);
  });
}
