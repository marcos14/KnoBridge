import { describe, expect, it } from "vitest";

import {
  acceptsChatFilters,
  DEFAULT_USAGE_SEARCH,
  hasChatFilters,
  parseUsageSearch,
  presetDays,
  searchDays,
  usageChatFilters,
  usagePeriod,
  usageSearchParams,
} from "./usagePeriod";

const NOW = new Date("2026-10-10T12:00:00Z");

describe("parseUsageSearch", () => {
  it("test_parse_usage_search_defaults_to_this_month_by_day", () => {
    expect(parseUsageSearch(new URLSearchParams())).toEqual(DEFAULT_USAGE_SEARCH);
  });

  it("test_parse_usage_search_reads_preset_and_group", () => {
    expect(parseUsageSearch(new URLSearchParams("period=last30&group=model"))).toEqual({
      preset: "last30",
      group: "model",
    });
  });

  it("test_parse_usage_search_ignores_unknown_values_and_days_outside_custom", () => {
    expect(parseUsageSearch(new URLSearchParams("period=year&group=user&from=2026-01-01"))).toEqual(
      DEFAULT_USAGE_SEARCH,
    );
  });

  it("test_parse_usage_search_keeps_only_valid_custom_days", () => {
    expect(
      parseUsageSearch(new URLSearchParams("period=custom&from=2026-09-01&to=2026-02-30")),
    ).toEqual({ preset: "custom", group: "day", from: "2026-09-01", to: undefined });
  });
});

describe("usageSearchParams", () => {
  it("test_usage_search_params_leave_defaults_out", () => {
    expect(usageSearchParams(DEFAULT_USAGE_SEARCH).toString()).toBe("");
  });

  it("test_usage_search_params_write_custom_days_and_group", () => {
    const params = usageSearchParams({
      preset: "custom",
      group: "product",
      from: "2026-09-01",
      to: "2026-09-30",
    });
    expect(params.toString()).toBe("period=custom&from=2026-09-01&to=2026-09-30&group=product");
  });

  it("test_usage_search_params_skip_missing_custom_days", () => {
    expect(usageSearchParams({ preset: "custom", group: "day" }).toString()).toBe("period=custom");
  });

  it("test_usage_search_params_drop_days_of_a_ready_made_period", () => {
    expect(
      usageSearchParams({ preset: "lastMonth", group: "day", from: "2026-09-01" }).toString(),
    ).toBe("period=lastMonth");
  });
});

const PRODUCT = "00000000-0000-4000-8000-0000000000f1";

describe("product and level filters", () => {
  it("test_parse_usage_search_reads_product_and_level", () => {
    expect(
      parseUsageSearch(new URLSearchParams(`group=level&product=${PRODUCT}&level=support`)),
    ).toEqual({ preset: "thisMonth", group: "level", product: PRODUCT, level: "support" });
  });

  it("test_parse_usage_search_drops_invalid_filters", () => {
    expect(parseUsageSearch(new URLSearchParams("product=x&level=admin"))).toEqual(
      DEFAULT_USAGE_SEARCH,
    );
  });

  it("test_parse_usage_search_drops_filters_of_an_embeddings_grouping", () => {
    expect(
      parseUsageSearch(new URLSearchParams(`group=source&product=${PRODUCT}&level=support`)),
    ).toEqual({ preset: "thisMonth", group: "source" });
  });

  it("test_usage_search_params_write_filters_only_where_they_apply", () => {
    expect(
      usageSearchParams({
        preset: "thisMonth",
        group: "day",
        product: PRODUCT,
        level: "end_user",
      }).toString(),
    ).toBe(`product=${PRODUCT}&level=end_user`);
    expect(
      usageSearchParams({ preset: "thisMonth", group: "collection", level: "end_user" }).toString(),
    ).toBe("group=collection");
  });

  it("test_usage_chat_filters_go_to_the_api_only_where_they_apply", () => {
    const search = { preset: "thisMonth" as const, product: PRODUCT, level: "support" as const };

    expect(usageChatFilters({ ...search, group: "model" })).toEqual({
      productId: PRODUCT,
      level: "support",
    });
    expect(usageChatFilters({ ...search, group: "source" })).toEqual({});
  });

  it("test_accepts_chat_filters_and_has_chat_filters", () => {
    expect(acceptsChatFilters("day")).toBe(true);
    expect(acceptsChatFilters("collection")).toBe(false);
    expect(hasChatFilters(DEFAULT_USAGE_SEARCH)).toBe(false);
    expect(hasChatFilters({ ...DEFAULT_USAGE_SEARCH, level: "support" })).toBe(true);
    expect(hasChatFilters({ ...DEFAULT_USAGE_SEARCH, product: PRODUCT })).toBe(true);
  });
});

describe("presetDays", () => {
  it("test_preset_days_this_month_runs_until_today", () => {
    expect(presetDays("thisMonth", NOW)).toEqual({ from: "2026-10-01", to: "2026-10-10" });
  });

  it("test_preset_days_last_month_is_the_whole_previous_month", () => {
    expect(presetDays("lastMonth", NOW)).toEqual({ from: "2026-09-01", to: "2026-09-30" });
    expect(presetDays("lastMonth", new Date("2026-01-15T00:00:00Z"))).toEqual({
      from: "2025-12-01",
      to: "2025-12-31",
    });
  });

  it("test_preset_days_last_30_includes_today", () => {
    expect(presetDays("last30", NOW)).toEqual({ from: "2026-09-11", to: "2026-10-10" });
  });

  it("test_preset_days_use_the_utc_day", () => {
    // 23:30 at UTC-3 is already the next day in UTC.
    expect(presetDays("thisMonth", new Date("2026-10-31T23:30:00Z"))).toEqual({
      from: "2026-10-01",
      to: "2026-10-31",
    });
  });
});

describe("searchDays and usagePeriod", () => {
  it("test_search_days_of_custom_are_the_chosen_ones", () => {
    expect(searchDays({ preset: "custom", group: "day", from: "2026-09-05" }, NOW)).toEqual({
      from: "2026-09-05",
      to: undefined,
    });
  });

  it("test_usage_period_is_half_open_in_utc", () => {
    expect(usagePeriod(DEFAULT_USAGE_SEARCH, NOW)).toEqual({
      from: "2026-10-01T00:00:00.000Z",
      to: "2026-10-11T00:00:00.000Z",
    });
  });

  it("test_usage_period_of_custom_without_days_leaves_the_api_default", () => {
    expect(usagePeriod({ preset: "custom", group: "day" }, NOW)).toEqual({
      from: undefined,
      to: undefined,
    });
  });

  it("test_usage_period_of_custom_counts_the_whole_last_day", () => {
    expect(
      usagePeriod({ preset: "custom", group: "day", from: "2026-09-01", to: "2026-09-30" }, NOW),
    ).toEqual({ from: "2026-09-01T00:00:00.000Z", to: "2026-10-01T00:00:00.000Z" });
  });
});
