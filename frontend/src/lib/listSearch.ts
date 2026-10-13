/**
 * Search, filters, sort and page of a workspace listing (assistants, providers, collections,
 * sources, members, runners), kept in the URL query string so a filtered view can be shared and
 * survives a reload: `?q=<text>&<filter>=<value>&sort=<field>&offset=<n>`. The API does the work
 * (`query`, the filters, `sort`, `limit`/`offset`); this module only reads and writes the URL.
 */

import { parseOffset } from "@/lib/pagination";

/** Longest `query` the listings accept (`docs/specs/indexacao.md`, "Listagens"). */
export const QUERY_MAX_LENGTH = 200;

/** What a listing accepts: a validator per filter and its sort values, the first the default. */
export interface ListSearchSpec<Filter extends string, Sort extends string> {
  filters: Readonly<Record<Filter, (value: string) => boolean>>;
  sorts: readonly [Sort, ...Sort[]];
}

export interface ListSearch<Filter extends string, Sort extends string> {
  /** Text searched by the API; empty means no search. */
  query: string;
  /** Chosen filters; an absent key is "all". */
  filters: Partial<Record<Filter, string>>;
  sort: Sort;
  offset: number;
}

/** Validator of a filter that takes one of `values`. */
export function oneOf(values: readonly string[]): (value: string) => boolean {
  return (value) => values.includes(value);
}

/** The text sent as `query`: trimmed and cut to the length the API accepts. */
export function normalizeQuery(text: string): string {
  return text.trim().slice(0, QUERY_MAX_LENGTH);
}

/**
 * Search read from the URL. Values the API would refuse (unknown filter value or sort) are
 * dropped, so a hand-edited link still opens a listing.
 */
export function parseListSearch<Filter extends string, Sort extends string>(
  params: URLSearchParams,
  spec: ListSearchSpec<Filter, Sort>,
): ListSearch<Filter, Sort> {
  const filters: Partial<Record<Filter, string>> = {};
  for (const key of Object.keys(spec.filters) as Filter[]) {
    const value = params.get(key);
    if (value !== null && spec.filters[key](value)) {
      filters[key] = value;
    }
  }
  const sort = spec.sorts.find((value) => value === params.get("sort")) ?? spec.sorts[0];
  return {
    query: normalizeQuery(params.get("q") ?? ""),
    filters,
    sort,
    offset: parseOffset(params.get("offset")),
  };
}

/** Query string of a search; no search, no filter, the default sort and page one leave no trace. */
export function listSearchParams<Filter extends string, Sort extends string>(
  search: ListSearch<Filter, Sort>,
  spec: ListSearchSpec<Filter, Sort>,
): URLSearchParams {
  const params = new URLSearchParams();
  if (search.query !== "") {
    params.set("q", search.query);
  }
  for (const key of Object.keys(spec.filters) as Filter[]) {
    const value = search.filters[key];
    if (value !== undefined) {
      params.set(key, value);
    }
  }
  if (search.sort !== spec.sorts[0]) {
    params.set("sort", search.sort);
  }
  if (search.offset > 0) {
    params.set("offset", String(search.offset));
  }
  return params;
}

/** Whether a search or a filter narrows the list (an empty result is then "nothing found"). */
export function hasListCriteria(search: ListSearch<string, string>): boolean {
  return search.query !== "" || Object.values(search.filters).some((value) => value !== undefined);
}

/** `"true"`/`"false"` of a boolean filter as the API takes it; absent stays absent. */
export function booleanFilter(value: string | undefined): boolean | undefined {
  return value === undefined ? undefined : value === "true";
}

/** Validator of a boolean filter. */
export const isBooleanFilter = oneOf(["true", "false"]);

const SORT_LABELS = {
  name: "nameAsc",
  "-name": "nameDesc",
  created_at: "oldest",
  "-created_at": "newest",
  "-updated_at": "recentlyUpdated",
  "-document_count": "mostDocuments",
  "-last_run_at": "lastRun",
  "-last_seen_at": "lastSeen",
  email: "emailAsc",
  role: "role",
  joined_at: "joinedOldest",
  "-joined_at": "joinedNewest",
} as const;

/** A sort the listing screens offer (each listing takes a subset). */
export type ListSort = keyof typeof SORT_LABELS;

/** i18n key of the label of a sort ("Nome (A–Z)", "Mais recentes primeiro"). */
export function sortLabelKey(sort: ListSort) {
  return `listToolbar.sorts.${SORT_LABELS[sort]}` as const;
}
