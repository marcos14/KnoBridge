import type { UsageGroup, UsageReport, UsageRow, UsageTotals } from "@/lib/api/usage";

import { PRODUCT_ID, OTHER_PRODUCT_ID } from "./factories";

/** Totals of the default report: embeddings and chat, three answers without a price. */
export function makeUsageTotals(overrides: Partial<UsageTotals> = {}): UsageTotals {
  return {
    embedding_tokens: 1_250_000,
    embedding_cost_usd: 0.025,
    runs: 14,
    unpriced_runs: 0,
    chat_input_tokens: 98_000,
    chat_output_tokens: 12_000,
    chat_cost_usd: 0.0584,
    answers: 120,
    unpriced_answers: 3,
    cost_usd: 0.0834,
    ...overrides,
  };
}

/** A row with every column empty (`null`) and no cost, to fill per grouping. */
export function makeUsageRow(overrides: Partial<UsageRow> = {}): UsageRow {
  return {
    key: "row",
    label: "Linha",
    embedding_tokens: null,
    embedding_cost_usd: null,
    runs: null,
    unpriced_runs: null,
    chat_input_tokens: null,
    chat_output_tokens: null,
    chat_cost_usd: null,
    answers: null,
    unpriced_answers: null,
    cost_usd: 0,
    ...overrides,
  };
}

/** A chat row (assistant, channel, key) with `answers` and `cost`. */
function chatRow(key: string, label: string, cost: number, answers: number, unpriced = 0) {
  return makeUsageRow({
    key,
    label,
    chat_input_tokens: answers * 800,
    chat_output_tokens: answers * 100,
    chat_cost_usd: cost,
    answers,
    unpriced_answers: unpriced,
    cost_usd: cost,
  });
}

/** An embeddings row (source, collection) with `tokens` and `cost`. */
function embeddingRow(key: string, label: string, cost: number, tokens: number) {
  return makeUsageRow({
    key,
    label,
    embedding_tokens: tokens,
    embedding_cost_usd: cost,
    runs: 7,
    unpriced_runs: 0,
    cost_usd: cost,
  });
}

/** Three UTC days from 2026-10-01: a cheap one, an empty one and the most expensive. */
export function makeUsageDays(): UsageRow[] {
  const day = (key: string, cost: number, tokens: number, answers: number) =>
    makeUsageRow({
      key,
      label: key,
      embedding_tokens: tokens,
      embedding_cost_usd: cost / 2,
      runs: tokens === 0 ? 0 : 1,
      unpriced_runs: 0,
      chat_input_tokens: answers * 800,
      chat_output_tokens: answers * 100,
      chat_cost_usd: cost / 2,
      answers,
      unpriced_answers: 0,
      cost_usd: cost,
    });
  return [
    day("2026-10-01", 0.02, 500_000, 40),
    day("2026-10-02", 0, 0, 0),
    day("2026-10-03", 0.06, 750_000, 80),
  ];
}

/** Rows of each grouping, in the API's order (cost descending, then label). */
export function makeUsageRows(group: UsageGroup): UsageRow[] {
  switch (group) {
    case "day":
      return makeUsageDays();
    case "product":
      return [
        chatRow(PRODUCT_ID, "Suporte ERP", 0.0584, 117),
        chatRow(OTHER_PRODUCT_ID, "Rascunho", 0, 3, 3),
      ];
    case "level":
      return [
        chatRow("end_user", "end_user", 0, 0),
        chatRow("support", "support", 0.0084, 20, 3),
        chatRow("product_dev", "product_dev", 0.05, 100),
      ];
    case "channel":
      return [chatRow("panel", "panel", 0.05, 100), chatRow("api", "api", 0.0084, 20, 3)];
    case "api_key":
      return [chatRow("6f1c0000-0000-4000-8000-000000000001", "Integração CRM", 0.0084, 20)];
    case "widget":
      return [chatRow("7a2d0000-0000-4000-8000-000000000001", "Site público", 0.0021, 9)];
    case "source":
      return [
        embeddingRow("src-1", "erp-core", 0.02, 1_000_000),
        embeddingRow("src-2", "manuais", 0.005, 250_000),
      ];
    case "collection":
      return [embeddingRow("col-1", "Código ERP", 0.025, 1_250_000)];
    case "model":
      return [
        chatRow("gpt-4.1-mini", "gpt-4.1-mini", 0.0584, 117),
        embeddingRow("text-embedding-3-small", "text-embedding-3-small", 0.025, 1_250_000),
      ];
  }
}

/** The report of `group` for October 2026 up to TEST_NOW's day (`[10-01, 10-11)`). */
export function makeUsageReport(
  group: UsageGroup = "day",
  overrides: Partial<UsageReport> = {},
): UsageReport {
  return {
    period_start: "2026-10-01T00:00:00Z",
    period_end: "2026-10-11T00:00:00Z",
    group_by: group,
    totals: makeUsageTotals(),
    rows: makeUsageRows(group),
    ...overrides,
  };
}

/** The CSV body of the export (a header, one row and the total). */
export const USAGE_CSV =
  "key,label,cost_usd\r\n2026-10-01,2026-10-01,0.020000\r\ntotal,Total,0.083400\r\n";
