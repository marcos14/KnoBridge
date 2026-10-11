import { describe, expect, it } from "vitest";

import { i18n } from "@/i18n";
import { makeRun } from "@/test/factories";

import {
  cronText,
  formatCount,
  formatDuration,
  formatUsd,
  runDuration,
  testFailureReason,
} from "./format";

const t = i18n.t.bind(i18n);
// Intl separates currency and amount with a no-break space.
const usd = (text: string) => text.replace(/\s/g, " ");

describe("formatUsd", () => {
  it("test_format_usd_keeps_small_costs_readable", () => {
    expect(usd(formatUsd(0.000048, "pt-BR"))).toBe("US$ 0,000048");
    expect(usd(formatUsd(0.001, "pt-BR"))).toBe("US$ 0,0010");
  });

  it("test_format_usd_uses_cents_from_one_cent_up", () => {
    expect(usd(formatUsd(1.5, "pt-BR"))).toBe("US$ 1,50");
    expect(usd(formatUsd(0, "pt-BR"))).toBe("US$ 0,00");
  });

  it("test_format_usd_shows_dash_for_unknown_cost", () => {
    expect(formatUsd(null, "pt-BR")).toBe("—");
  });
});

describe("formatCount", () => {
  it("test_format_count_groups_thousands", () => {
    expect(formatCount(51000, "pt-BR")).toBe("51.000");
  });
});

describe("formatDuration", () => {
  it.each([
    [0, "0 s"],
    [45_000, "45 s"],
    [60_000, "1 min"],
    [119_000, "1 min 59 s"],
    [3_600_000, "1 h"],
    [7_530_000, "2 h 5 min"],
    [-5_000, "0 s"],
  ])("test_format_duration_of_%d_ms", (milliseconds, expected) => {
    expect(formatDuration(milliseconds)).toBe(expected);
  });
});

describe("runDuration", () => {
  const now = new Date("2026-10-10T12:00:00Z");

  it("test_run_duration_of_a_finished_run", () => {
    expect(runDuration(makeRun(), now)).toBe("59 s");
  });

  it("test_run_duration_of_a_running_run_counts_until_now", () => {
    const run = makeRun({ started_at: "2026-10-10T11:58:00Z", finished_at: null });
    expect(runDuration(run, now)).toBe("2 min");
  });

  it("test_run_duration_is_undefined_before_the_run_starts", () => {
    expect(runDuration(makeRun({ started_at: null, finished_at: null }), now)).toBeUndefined();
  });
});

describe("cronText", () => {
  it.each([
    ["* * * * *", "A cada minuto"],
    ["*/1 * * * *", "A cada minuto"],
    ["*/15 * * * *", "A cada 15 minutos"],
    ["5 * * * *", "A cada hora, no minuto 5"],
    ["0 */1 * * *", "A cada hora, no minuto 0"],
    ["30 */6 * * *", "A cada 6 horas, no minuto 30"],
    ["0 3 * * *", "Todos os dias às 03:00 (UTC)"],
    ["0 6 * * 1-5", "De segunda a sexta às 06:00 (UTC)"],
    ["0 2 * * 0,6", "Toda semana: domingo e sábado, às 02:00 (UTC)"],
    ["0 4 10 * *", "Todo dia 10 do mês às 04:00 (UTC)"],
    ["0 3 * 1 *", "Expressão personalizada: o servidor confere ao salvar."],
  ])("test_cron_text_of_%s", (cron, expected) => {
    expect(cronText(cron, t, "pt-BR")).toBe(expected);
  });
});

describe("testFailureReason", () => {
  it.each([
    ["runner_offline", "o runner está offline"],
    ["runner_revoked", "o runner foi revogado"],
    ["repository_not_served", "o runner não informou esse repositório no último contato"],
  ])("test_test_failure_reason_explains_runner_%s", (reason, expected) => {
    expect(testFailureReason({ code: "source_unavailable", details: { reason } }, t)).toBe(
      expected,
    );
  });

  it("test_test_failure_reason_falls_back_to_the_error_code", () => {
    const unavailable = t("apiErrors.source_unavailable");
    const reasonOf = (details: unknown) =>
      testFailureReason({ code: "source_unavailable", details }, t);

    expect(reasonOf({ reason: "other" })).toBe(unavailable);
    expect(reasonOf(null)).toBe(unavailable);
    expect(reasonOf("x")).toBe(unavailable);
    expect(reasonOf({})).toBe(unavailable);
    expect(
      testFailureReason({ code: "source_timeout", details: { reason: "runner_offline" } }, t),
    ).toBe(t("apiErrors.source_timeout"));
  });
});
