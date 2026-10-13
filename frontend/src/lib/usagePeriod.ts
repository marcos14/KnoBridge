/**
 * Period and grouping of the usage screen, kept in the URL query string, and the instants the API
 * takes for them. Usage is counted in UTC days (`docs/specs/uso-e-custos.md`), so the periods here
 * are UTC days too: the `day` rows and the CSV file name then match what the screen shows.
 */

import type { ResponseLevel } from "./api/levels";
import type { UsageGroup } from "./api/usage";
import { validDay } from "./days";
import { parseLevel } from "./responseLevels";
import { isUuid } from "./uuid";

export const USAGE_PRESETS = ["thisMonth", "lastMonth", "last30", "custom"] as const;
export type UsagePreset = (typeof USAGE_PRESETS)[number];

/** Groupings in the order the screen offers them; `day` first, the one with the chart. */
export const USAGE_GROUPS = [
  "day",
  "source",
  "collection",
  "product",
  "level",
  "channel",
  "api_key",
  "model",
] as const satisfies readonly UsageGroup[];

/**
 * What the screen shows; `from` and `to` (inclusive UTC days) only for the custom period;
 * `product` and `level` restrict the chat answers (never with a grouping of embeddings only).
 */
export interface UsageSearch {
  preset: UsagePreset;
  group: UsageGroup;
  from?: string;
  to?: string;
  product?: string;
  level?: ResponseLevel;
}

/**
 * Whether the product and level filters apply to a grouping: sources and collections only have
 * embeddings, which belong to no product or level, so the API refuses the filters with them.
 */
export function acceptsChatFilters(group: UsageGroup): boolean {
  return group !== "source" && group !== "collection";
}

/** Whether the report is restricted to a product or level (then it counts only the chat). */
export function hasChatFilters(search: UsageSearch): boolean {
  return search.product !== undefined || search.level !== undefined;
}

export const DEFAULT_USAGE_SEARCH: UsageSearch = { preset: "thisMonth", group: "day" };

/** Inclusive UTC days `YYYY-MM-DD`. */
export interface DayRange {
  from: string;
  to: string;
}

/** The period as the API takes it: `[from, to)`, ISO 8601 UTC instants; missing = API default. */
export interface UsagePeriod {
  from?: string;
  to?: string;
}

function oneOf<T extends string>(values: readonly T[], value: string | null): T | undefined {
  return values.find((item) => item === value);
}

/** The screen state from the query string; anything the API would refuse falls back to default. */
export function parseUsageSearch(params: URLSearchParams): UsageSearch {
  const preset = oneOf(USAGE_PRESETS, params.get("period")) ?? DEFAULT_USAGE_SEARCH.preset;
  const group = oneOf(USAGE_GROUPS, params.get("group")) ?? DEFAULT_USAGE_SEARCH.group;
  const search: UsageSearch =
    preset === "custom"
      ? { preset, group, from: validDay(params.get("from")), to: validDay(params.get("to")) }
      : { preset, group };
  if (!acceptsChatFilters(group)) {
    return search;
  }
  const product = params.get("product");
  return {
    ...search,
    product: isUuid(product) ? product : undefined,
    level: parseLevel(params.get("level")),
  };
}

/** The query string of `search`, leaving the defaults out so a plain link stays short. */
export function usageSearchParams(search: UsageSearch): URLSearchParams {
  const params = new URLSearchParams();
  if (search.preset !== DEFAULT_USAGE_SEARCH.preset) {
    params.set("period", search.preset);
  }
  if (search.preset === "custom") {
    if (search.from !== undefined) {
      params.set("from", search.from);
    }
    if (search.to !== undefined) {
      params.set("to", search.to);
    }
  }
  if (search.group !== DEFAULT_USAGE_SEARCH.group) {
    params.set("group", search.group);
  }
  if (acceptsChatFilters(search.group)) {
    if (search.product !== undefined) {
      params.set("product", search.product);
    }
    if (search.level !== undefined) {
      params.set("level", search.level);
    }
  }
  return params;
}

/** The product and level sent to the API: none with a grouping of embeddings only. */
export function usageChatFilters(search: UsageSearch): {
  productId?: string;
  level?: ResponseLevel;
} {
  return acceptsChatFilters(search.group) ? { productId: search.product, level: search.level } : {};
}

/** The UTC day of `date` plus `shift` days, as `YYYY-MM-DD`. */
function utcDay(date: Date, shift = 0): string {
  const day = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()));
  day.setUTCDate(day.getUTCDate() + shift);
  return day.toISOString().slice(0, 10);
}

/** Midnight UTC of the day `day` plus `shift` days, as an ISO 8601 instant. */
function utcDayStart(day: string, shift = 0): string {
  const start = new Date(`${day}T00:00:00Z`);
  start.setUTCDate(start.getUTCDate() + shift);
  return start.toISOString();
}

/** The inclusive UTC days of a ready-made period, as of `now` (today counts). */
export function presetDays(preset: Exclude<UsagePreset, "custom">, now: Date): DayRange {
  const year = now.getUTCFullYear();
  const month = now.getUTCMonth();
  switch (preset) {
    case "thisMonth":
      return { from: utcDay(new Date(Date.UTC(year, month, 1))), to: utcDay(now) };
    case "lastMonth":
      return {
        from: utcDay(new Date(Date.UTC(year, month - 1, 1))),
        to: utcDay(new Date(Date.UTC(year, month, 0))),
      };
    case "last30":
      return { from: utcDay(now, -29), to: utcDay(now) };
  }
}

/** The inclusive days the screen shows for `search` (custom: what was chosen, maybe nothing). */
export function searchDays(search: UsageSearch, now: Date): Partial<DayRange> {
  return search.preset === "custom"
    ? { from: search.from, to: search.to }
    : presetDays(search.preset, now);
}

/**
 * The period sent to the API: `[midnight of "from", midnight after "to")` in UTC, so the whole
 * last day counts. A custom period without a day leaves that end to the API (30 days, now).
 */
export function usagePeriod(search: UsageSearch, now: Date): UsagePeriod {
  const { from, to } = searchDays(search, now);
  return {
    from: from === undefined ? undefined : utcDayStart(from),
    to: to === undefined ? undefined : utcDayStart(to, 1),
  };
}
