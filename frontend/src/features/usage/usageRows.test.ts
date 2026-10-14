import { describe, expect, it } from "vitest";

import { makeUsageRow } from "@/test/usageFactories";

import {
  firstDirection,
  formatUsageDay,
  isPartialRow,
  nextSort,
  sortUsageRows,
  usageColumns,
} from "./usageRows";

const labels = (rows: { label: string }[]) => rows.map(({ label }) => label);

describe("usageColumns", () => {
  it("test_usage_columns_of_embedding_groups", () => {
    expect(usageColumns("source")).toEqual([
      "embedding_tokens",
      "embedding_cost_usd",
      "runs",
      "cost_usd",
    ]);
    expect(usageColumns("collection")).toEqual(usageColumns("source"));
  });

  it("test_usage_columns_of_chat_groups", () => {
    const chat = [
      "chat_input_tokens",
      "chat_output_tokens",
      "chat_cost_usd",
      "answers",
      "cost_usd",
    ];
    expect(usageColumns("product")).toEqual(chat);
    expect(usageColumns("level")).toEqual(chat);
    expect(usageColumns("channel")).toEqual(chat);
    expect(usageColumns("api_key")).toEqual(chat);
    expect(usageColumns("widget")).toEqual(chat);
    // Filtered by product or level, models and days have only the chat.
    expect(usageColumns("model", true)).toEqual(chat);
    expect(usageColumns("day", true)).toEqual(chat);
  });

  it("test_usage_columns_of_model_and_day_have_both_sides", () => {
    expect(usageColumns("model")).toHaveLength(8);
    expect(usageColumns("day")).toEqual(usageColumns("model"));
  });
});

describe("sorting", () => {
  const rows = [
    makeUsageRow({ key: "b", label: "Beta", cost_usd: 2, runs: null }),
    makeUsageRow({ key: "a", label: "Alfa", cost_usd: 2, runs: 5 }),
    makeUsageRow({ key: "c", label: "Gama", cost_usd: 9, runs: 1 }),
    makeUsageRow({ key: "d", label: "Delta", cost_usd: 0, runs: null }),
  ];

  it("test_first_direction_is_ascending_for_names_and_descending_for_numbers", () => {
    expect(firstDirection("label")).toBe("asc");
    expect(firstDirection("cost_usd")).toBe("desc");
  });

  it("test_next_sort_flips_the_same_column_and_resets_another", () => {
    expect(nextSort(null, "runs")).toEqual({ key: "runs", direction: "desc" });
    expect(nextSort({ key: "runs", direction: "desc" }, "runs")).toEqual({
      key: "runs",
      direction: "asc",
    });
    expect(nextSort({ key: "runs", direction: "asc" }, "runs")).toEqual({
      key: "runs",
      direction: "desc",
    });
    expect(nextSort({ key: "runs", direction: "asc" }, "label")).toEqual({
      key: "label",
      direction: "asc",
    });
  });

  it("test_sort_usage_rows_without_sort_keeps_the_api_order", () => {
    const sorted = sortUsageRows(rows, null);
    expect(labels(sorted)).toEqual(["Beta", "Alfa", "Gama", "Delta"]);
    expect(sorted).not.toBe(rows);
  });

  it("test_sort_usage_rows_by_label_both_ways", () => {
    expect(labels(sortUsageRows(rows, { key: "label", direction: "asc" }))).toEqual([
      "Alfa",
      "Beta",
      "Delta",
      "Gama",
    ]);
    expect(labels(sortUsageRows(rows, { key: "label", direction: "desc" }))).toEqual([
      "Gama",
      "Delta",
      "Beta",
      "Alfa",
    ]);
  });

  it("test_sort_usage_rows_by_number_breaks_ties_by_label", () => {
    expect(labels(sortUsageRows(rows, { key: "cost_usd", direction: "desc" }))).toEqual([
      "Gama",
      "Alfa",
      "Beta",
      "Delta",
    ]);
    expect(labels(sortUsageRows(rows, { key: "cost_usd", direction: "asc" }))).toEqual([
      "Delta",
      "Alfa",
      "Beta",
      "Gama",
    ]);
  });

  it("test_sort_usage_rows_puts_missing_values_last_either_way", () => {
    expect(labels(sortUsageRows(rows, { key: "runs", direction: "desc" }))).toEqual([
      "Alfa",
      "Gama",
      "Beta",
      "Delta",
    ]);
    expect(labels(sortUsageRows(rows, { key: "runs", direction: "asc" }))).toEqual([
      "Gama",
      "Alfa",
      "Beta",
      "Delta",
    ]);
  });
});

describe("row helpers", () => {
  it("test_is_partial_row_when_runs_or_answers_have_no_price", () => {
    expect(isPartialRow(makeUsageRow())).toBe(false);
    expect(isPartialRow(makeUsageRow({ unpriced_runs: 0, unpriced_answers: 0 }))).toBe(false);
    expect(isPartialRow(makeUsageRow({ unpriced_runs: 1 }))).toBe(true);
    expect(isPartialRow(makeUsageRow({ unpriced_answers: 2 }))).toBe(true);
  });

  it("test_format_usage_day_reads_the_utc_day", () => {
    expect(formatUsageDay("2026-10-01", "pt-BR")).toBe("1 de out. de 2026");
  });
});
