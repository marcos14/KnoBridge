import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { Role } from "@/lib/api/auth";
import type { UsageGroup } from "@/lib/api/usage";
import { stubDownloads } from "@/test/downloads";
import { makeMe, makeWorkspace, WORKSPACE_ID } from "@/test/factories";
import {
  meAs,
  usageAs,
  usageCsvFails,
  usageCsvPending,
  usageCsvWithoutName,
  usageFails,
  usageRecorder,
} from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";
import { makeUsageReport, makeUsageRow, makeUsageTotals } from "@/test/usageFactories";

const PATH = `/w/${WORKSPACE_ID}/usage`;
// Intl separates currency and amount with a no-break space.
const usd = (text: string | null | undefined) => (text ?? "").replace(/\s/g, " ");

function asRole(role: Role) {
  server.use(meAs(makeMe({ workspaces: [makeWorkspace({ role })] })));
}

function record(...args: Parameters<typeof usageRecorder>) {
  const recorder = usageRecorder(...args);
  server.use(...recorder.handlers);
  return recorder;
}

function last(queries: URLSearchParams[]): Record<string, string> {
  return Object.fromEntries(queries.at(-1) ?? []);
}

async function renderUsage(path = PATH, table = "Uso por Dia") {
  const user = userEvent.setup();
  const rendered = renderWithProviders({ path });
  await screen.findByRole("table", { name: table });
  return { user, ...rendered };
}

function bodyRows(table: string): string[][] {
  const element = screen.getByRole("table", { name: table });
  const body = element.querySelector("tbody");
  return within(body as HTMLElement)
    .getAllByRole("row")
    .map((row) =>
      within(row)
        .getAllByRole("cell")
        .map((cell) => usd(cell.textContent)),
    );
}

async function pick(user: ReturnType<typeof userEvent.setup>, label: string, option: string) {
  await user.click(screen.getByRole("combobox", { name: label }));
  await user.click(await screen.findByRole("option", { name: option }));
}

function figures(region: HTMLElement): [string | null, string][] {
  return within(region)
    .getAllByRole("term")
    .map((term) => [term.textContent, usd(term.nextElementSibling?.textContent)]);
}

describe("UsagePage report", () => {
  it("test_usage_asks_this_month_by_day_by_default", async () => {
    const recorder = record();
    await renderUsage();

    expect(screen.getByRole("heading", { level: 1, name: "Uso e custos" })).toBeVisible();
    expect(last(recorder.reportQueries)).toEqual({
      group_by: "day",
      from: "2026-10-01T00:00:00.000Z",
      to: "2026-10-11T00:00:00.000Z",
    });
    expect(screen.getByRole("combobox", { name: "Período" })).toHaveTextContent("Este mês");
    expect(screen.getByRole("combobox", { name: "Agrupar por" })).toHaveTextContent("Dia");
  });

  it("test_usage_shows_the_period_totals", async () => {
    record();
    await renderUsage();

    const totals = screen.getByRole("region", { name: "Totais do período" });
    expect(
      within(totals).getByText("De 1 de out. de 2026 a 10 de out. de 2026 (UTC)"),
    ).toBeVisible();
    const cost = within(totals).getByRole("region", { name: "Custo estimado" });
    expect(usd(within(cost).getByText(/US\$/).textContent)).toBe("US$ 0,0834");
    expect(figures(within(totals).getByRole("region", { name: "Embeddings" }))).toEqual([
      ["Tokens", "1.250.000"],
      ["Custo", "US$ 0,025"],
      ["Execuções", "14"],
    ]);
    expect(figures(within(totals).getByRole("region", { name: "Chat" }))).toEqual([
      ["Tokens de entrada", "98.000"],
      ["Tokens de saída", "12.000"],
      ["Custo", "US$ 0,0584"],
      ["Respostas", "120"],
    ]);
  });

  it("test_usage_warns_of_partial_cost_when_items_have_no_price", async () => {
    record((group) => makeUsageReport(group, { totals: makeUsageTotals({ unpriced_runs: 1 }) }));
    await renderUsage();

    const note = screen.getByRole("note", { name: "Custo parcial" });
    expect(within(note).getByText("1 execução de indexação sem preço")).toBeVisible();
    expect(within(note).getByText("3 respostas do chat sem preço")).toBeVisible();
  });

  it("test_usage_without_unpriced_items_has_no_warning", async () => {
    record((group) => makeUsageReport(group, { totals: makeUsageTotals({ unpriced_answers: 0 }) }));
    await renderUsage();

    expect(screen.queryByRole("note", { name: "Custo parcial" })).not.toBeInTheDocument();
  });

  it("test_usage_by_day_lists_every_day_with_both_sides_and_the_total", async () => {
    record();
    await renderUsage();

    const headers = within(screen.getByRole("table", { name: "Uso por Dia" }))
      .getAllByRole("columnheader")
      .map((header) => header.textContent);
    expect(headers).toEqual([
      "Dia",
      "Tokens de embedding",
      "Custo de embedding",
      "Execuções",
      "Tokens de entrada",
      "Tokens de saída",
      "Custo do chat",
      "Respostas",
      "Custo total",
    ]);
    const rows = bodyRows("Uso por Dia");
    expect(rows.map((row) => row[0])).toEqual([
      "1 de out. de 2026",
      "2 de out. de 2026",
      "3 de out. de 2026",
    ]);
    expect(rows[0]).toEqual([
      "1 de out. de 2026",
      "500.000",
      "US$ 0,01",
      "1",
      "32.000",
      "4.000",
      "US$ 0,01",
      "40",
      "US$ 0,02",
    ]);
    const footer = screen.getByRole("table", { name: "Uso por Dia" }).querySelector("tfoot");
    expect(usd(footer?.textContent)).toContain("Total");
    expect(usd(footer?.textContent)).toContain("US$ 0,0834");
  });

  it("test_usage_by_day_draws_a_bar_per_day", async () => {
    record();
    await renderUsage();

    const chart = screen.getByRole("list", { name: /Custo estimado por dia/ });
    const bars = within(chart).getAllByRole("listitem");
    expect(bars.map((bar) => usd(bar.getAttribute("aria-label")))).toEqual([
      "1 de out. de 2026: US$ 0,02",
      "2 de out. de 2026: US$ 0,00",
      "3 de out. de 2026: US$ 0,06",
    ]);
    expect(usd(chart.getAttribute("aria-label"))).toBe(
      "Custo estimado por dia, de 1 de out. de 2026 a 3 de out. de 2026; maior valor US$ 0,06",
    );
  });

  it("test_usage_chart_says_when_the_period_had_no_cost", async () => {
    record((group) =>
      makeUsageReport(group, { rows: [makeUsageRow({ key: "2026-10-01", label: "2026-10-01" })] }),
    );
    await renderUsage();

    expect(screen.getByText("Sem custo no período.")).toBeVisible();
    expect(screen.queryByRole("list", { name: /Custo estimado por dia/ })).not.toBeInTheDocument();
  });

  it("test_usage_without_rows_shows_the_empty_table_and_no_chart", async () => {
    record((group) => makeUsageReport(group, { rows: [] }));
    await renderUsage();

    expect(screen.getByText("Nenhum uso no período.")).toBeVisible();
    expect(screen.queryByText("Custo por dia")).not.toBeInTheDocument();
  });

  it("test_usage_marks_rows_with_partial_cost", async () => {
    record();
    await renderUsage(`${PATH}?group=assistant`, "Uso por Assistente");

    const table = screen.getByRole("table", { name: "Uso por Assistente" });
    const marks = within(table).getAllByRole("img", {
      name: "Custo parcial: há itens sem preço neste grupo",
    });
    expect(marks).toHaveLength(1);
    expect(marks[0]?.closest("tr")).toHaveTextContent("Rascunho");
    expect(screen.queryByText("Custo por dia")).not.toBeInTheDocument();
  });

  it("test_usage_by_channel_translates_the_channels", async () => {
    record();
    await renderUsage(`${PATH}?group=channel`, "Uso por Canal");

    expect(bodyRows("Uso por Canal").map((row) => row[0])).toEqual(["Painel", "API"]);
  });

  it("test_usage_by_source_shows_only_embedding_columns", async () => {
    record();
    await renderUsage(`${PATH}?group=source`, "Uso por Fonte");

    const headers = within(screen.getByRole("table", { name: "Uso por Fonte" }))
      .getAllByRole("columnheader")
      .map((header) => header.textContent);
    expect(headers).toEqual([
      "Fonte",
      "Tokens de embedding",
      "Custo de embedding",
      "Execuções",
      "Custo total",
    ]);
    expect(bodyRows("Uso por Fonte")[0]).toEqual([
      "erp-core",
      "1.000.000",
      "US$ 0,02",
      "7",
      "US$ 0,02",
    ]);
  });

  it("test_usage_table_sorts_by_a_clicked_column", async () => {
    record();
    const { user } = await renderUsage(`${PATH}?group=source`, "Uso por Fonte");
    const table = "Uso por Fonte";
    const header = (name: string) =>
      within(screen.getByRole("table", { name: table })).getByRole("columnheader", { name });

    expect(header("Fonte")).toHaveAttribute("aria-sort", "none");
    await user.click(within(header("Fonte")).getByRole("button"));
    expect(header("Fonte")).toHaveAttribute("aria-sort", "ascending");
    expect(bodyRows(table).map((row) => row[0])).toEqual(["erp-core", "manuais"]);

    await user.click(within(header("Fonte")).getByRole("button"));
    expect(header("Fonte")).toHaveAttribute("aria-sort", "descending");
    expect(bodyRows(table).map((row) => row[0])).toEqual(["manuais", "erp-core"]);

    await user.click(within(header("Custo total")).getByRole("button"));
    expect(header("Custo total")).toHaveAttribute("aria-sort", "descending");
    expect(header("Fonte")).toHaveAttribute("aria-sort", "none");
    expect(bodyRows(table).map((row) => row[0])).toEqual(["erp-core", "manuais"]);
  });
});

describe("UsagePage filters", () => {
  it.each<[string, string, string]>([
    ["Mês passado", "2026-09-01T00:00:00.000Z", "2026-10-01T00:00:00.000Z"],
    ["Últimos 30 dias", "2026-09-11T00:00:00.000Z", "2026-10-11T00:00:00.000Z"],
  ])("test_usage_preset_%s_sends_its_period", async (preset, from, to) => {
    const recorder = record();
    const { user, router } = await renderUsage();

    await pick(user, "Período", preset);

    await waitFor(() => {
      expect(last(recorder.reportQueries)).toEqual({ group_by: "day", from, to });
    });
    expect(router.state.location.search).toContain("period=");
  });

  it("test_usage_custom_period_starts_from_the_current_days_and_applies_changes", async () => {
    const recorder = record();
    const { user, router } = await renderUsage();

    await pick(user, "Período", "Personalizado");
    const from = screen.getByLabelText("De");
    const to = screen.getByLabelText("Até");
    expect(from).toHaveValue("2026-10-01");
    expect(to).toHaveValue("2026-10-10");

    fireEvent.change(from, { target: { value: "2026-08-01" } });
    fireEvent.change(screen.getByLabelText("Até"), { target: { value: "2026-08-31" } });

    await waitFor(() => {
      expect(last(recorder.reportQueries)).toEqual({
        group_by: "day",
        from: "2026-08-01T00:00:00.000Z",
        to: "2026-09-01T00:00:00.000Z",
      });
    });
    expect(router.state.location.search).toBe("?period=custom&from=2026-08-01&to=2026-08-31");
  });

  it("test_usage_custom_period_with_cleared_days_leaves_the_api_default", async () => {
    const recorder = record();
    await renderUsage(`${PATH}?period=custom&from=2026-08-01&to=2026-08-31`);

    fireEvent.change(screen.getByLabelText("De"), { target: { value: "" } });
    fireEvent.change(screen.getByLabelText("Até"), { target: { value: "" } });

    await waitFor(() => {
      expect(last(recorder.reportQueries)).toEqual({ group_by: "day" });
    });
  });

  it("test_usage_going_back_to_a_preset_hides_the_days", async () => {
    const { user } = await renderUsage(`${PATH}?period=custom&from=2026-08-01&to=2026-08-31`);

    await pick(user, "Período", "Este mês");

    await waitFor(() => {
      expect(screen.queryByLabelText("De")).not.toBeInTheDocument();
    });
  });

  it.each<[string, UsageGroup, string]>([
    ["Fonte", "source", "Uso por Fonte"],
    ["Coleção", "collection", "Uso por Coleção"],
    ["Assistente", "assistant", "Uso por Assistente"],
    ["Canal", "channel", "Uso por Canal"],
    ["Chave de API", "api_key", "Uso por Chave de API"],
    ["Modelo", "model", "Uso por Modelo"],
  ])("test_usage_group_%s_asks_the_api", async (option, group, table) => {
    const recorder = record();
    const { user } = await renderUsage();

    await pick(user, "Agrupar por", option);

    expect(await screen.findByRole("table", { name: table })).toBeVisible();
    expect(last(recorder.reportQueries).group_by).toBe(group);
  });
});

describe("UsagePage errors", () => {
  it("test_usage_period_too_long_is_explained_and_can_be_retried", async () => {
    server.use(usageFails(422, "usage_period_too_long"));
    const user = userEvent.setup();
    renderWithProviders({ path: `${PATH}?period=custom&from=2024-01-01&to=2026-10-01` });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não foi possível carregar o uso. O período pode ter no máximo 366 dias.",
    );
    server.use(usageAs());
    await user.click(screen.getByRole("button", { name: "Tentar novamente" }));

    expect(await screen.findByRole("table", { name: "Uso por Dia" })).toBeVisible();
  });
});

describe("UsagePage CSV export", () => {
  let downloads: ReturnType<typeof stubDownloads>;

  beforeEach(() => {
    downloads = stubDownloads();
  });

  afterEach(() => {
    downloads.restore();
  });

  it("test_usage_exports_the_report_as_csv", async () => {
    const recorder = record();
    const { user } = await renderUsage(`${PATH}?group=model`, "Uso por Modelo");

    await user.click(screen.getByRole("button", { name: "Exportar CSV" }));

    await waitFor(() => {
      expect(downloads.saved).toHaveLength(1);
    });
    expect(downloads.saved[0]?.name).toBe("knobridge-uso-model-2026-10-01-2026-10-11.csv");
    expect(last(recorder.csvQueries)).toEqual({
      group_by: "model",
      from: "2026-10-01T00:00:00.000Z",
      to: "2026-10-11T00:00:00.000Z",
    });
    expect(await downloads.blobs[0]?.text()).toContain("total,Total,0.083400");
  });

  it("test_usage_export_without_file_name_uses_the_grouping", async () => {
    record();
    server.use(usageCsvWithoutName);
    const { user } = await renderUsage();

    await user.click(screen.getByRole("button", { name: "Exportar CSV" }));

    await waitFor(() => {
      expect(downloads.saved[0]?.name).toBe("knobridge-uso-day.csv");
    });
  });

  it("test_usage_export_in_progress_disables_the_button", async () => {
    record();
    server.use(usageCsvPending);
    const { user } = await renderUsage();

    await user.click(screen.getByRole("button", { name: "Exportar CSV" }));

    expect(await screen.findByRole("button", { name: "Exportando…" })).toBeDisabled();
  });

  it("test_usage_export_failure_is_shown", async () => {
    record();
    server.use(usageCsvFails(403, "forbidden"));
    const { user } = await renderUsage();

    await user.click(screen.getByRole("button", { name: "Exportar CSV" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /^Não foi possível exportar o CSV: /,
    );
    expect(downloads.saved).toHaveLength(0);
  });
});

describe("UsagePage roles", () => {
  it.each<Role>(["owner", "admin"])("test_usage_is_open_to_%s", async (role) => {
    asRole(role);
    record();
    await renderUsage();

    const nav = screen.getByRole("navigation", { name: "Navegação principal" });
    expect(within(nav).getByRole("link", { name: "Uso e custos" })).toHaveAttribute("href", PATH);
  });

  it.each<Role>(["editor", "viewer"])("test_usage_is_closed_to_%s", async (role) => {
    asRole(role);
    const recorder = record();
    renderWithProviders({ path: PATH });

    expect(await screen.findByRole("heading", { level: 1, name: "Acesso negado" })).toBeVisible();
    const nav = screen.getByRole("navigation", { name: "Navegação principal" });
    expect(within(nav).queryByRole("link", { name: "Uso e custos" })).not.toBeInTheDocument();
    expect(recorder.reportQueries).toHaveLength(0);
  });
});
