import { describe, expect, it } from "vitest";

import {
  booleanFilter,
  hasListCriteria,
  isBooleanFilter,
  type ListSearchSpec,
  listSearchParams,
  normalizeQuery,
  oneOf,
  parseListSearch,
  QUERY_MAX_LENGTH,
  sortLabelKey,
} from "./listSearch";

const SPEC: ListSearchSpec<"kind" | "active", "name" | "-name" | "-created_at"> = {
  filters: { kind: oneOf(["git", "folder"]), active: isBooleanFilter },
  sorts: ["name", "-name", "-created_at"],
};

describe("parseListSearch", () => {
  it("test_parse_list_search_reads_query_filters_sort_and_offset", () => {
    const search = parseListSearch(
      new URLSearchParams("q=%20erp%20&kind=git&active=false&sort=-name&offset=40"),
      SPEC,
    );

    expect(search).toEqual({
      query: "erp",
      filters: { kind: "git", active: "false" },
      sort: "-name",
      offset: 40,
    });
  });

  it("test_parse_list_search_drops_values_the_api_refuses", () => {
    const search = parseListSearch(
      new URLSearchParams("kind=svn&active=yes&sort=size&offset=-3"),
      SPEC,
    );

    expect(search).toEqual({ query: "", filters: {}, sort: "name", offset: 0 });
  });

  it("test_parse_list_search_cuts_a_long_query", () => {
    const search = parseListSearch(new URLSearchParams({ q: "a".repeat(300) }), SPEC);

    expect(search.query).toHaveLength(QUERY_MAX_LENGTH);
  });
});

describe("listSearchParams", () => {
  it("test_list_search_params_writes_only_what_differs_from_the_default", () => {
    const params = listSearchParams({ query: "", filters: {}, sort: "name", offset: 0 }, SPEC);

    expect(params.toString()).toBe("");
  });

  it("test_list_search_params_round_trips_a_search", () => {
    const search = {
      query: "erp core",
      filters: { kind: "folder", active: "true" },
      sort: "-created_at" as const,
      offset: 20,
    };

    const params = listSearchParams(search, SPEC);

    expect(params.toString()).toBe("q=erp+core&kind=folder&active=true&sort=-created_at&offset=20");
    expect(parseListSearch(params, SPEC)).toEqual(search);
  });
});

describe("helpers", () => {
  it("test_has_list_criteria_counts_query_and_filters_not_sort", () => {
    expect(hasListCriteria({ query: "", filters: {}, sort: "-name", offset: 20 })).toBe(false);
    expect(hasListCriteria({ query: "x", filters: {}, sort: "name", offset: 0 })).toBe(true);
    expect(hasListCriteria({ query: "", filters: { kind: "git" }, sort: "name", offset: 0 })).toBe(
      true,
    );
  });

  it("test_normalize_query_trims_and_cuts", () => {
    expect(normalizeQuery("  nota  ")).toBe("nota");
    expect(normalizeQuery(` ${"b".repeat(250)}`)).toHaveLength(QUERY_MAX_LENGTH);
  });

  it("test_sort_label_key_names_the_i18n_label", () => {
    expect(sortLabelKey("name")).toBe("listToolbar.sorts.nameAsc");
    expect(sortLabelKey("-last_seen_at")).toBe("listToolbar.sorts.lastSeen");
  });

  it("test_boolean_filter_maps_to_the_api_value", () => {
    expect(booleanFilter(undefined)).toBeUndefined();
    expect(booleanFilter("true")).toBe(true);
    expect(booleanFilter("false")).toBe(false);
  });
});
