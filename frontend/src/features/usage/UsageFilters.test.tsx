import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { stubDownloads } from "@/test/downloads";
import { PRODUCT_ID, WORKSPACE_ID } from "@/test/factories";
import { usageRecorder } from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

const PATH = `/w/${WORKSPACE_ID}/usage`;
const CHAT_ONLY =
  "Os filtros de produto e nível valem só para o chat: agrupando por fonte ou coleção, eles ficam desligados.";
const FILTERED =
  "Filtrado por produto ou nível: só o chat entra na conta, porque embeddings não pertencem a um produto nem a um nível.";

function record() {
  const recorder = usageRecorder();
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

async function pick(user: ReturnType<typeof userEvent.setup>, label: string, option: string) {
  await user.click(screen.getByRole("combobox", { name: label }));
  await user.click(await screen.findByRole("option", { name: option }));
}

function headers(table: string): (string | null)[] {
  return within(screen.getByRole("table", { name: table }))
    .getAllByRole("columnheader")
    .map((header) => header.textContent);
}

describe("UsagePage product and level filters", () => {
  let downloads: ReturnType<typeof stubDownloads>;

  beforeEach(() => {
    downloads = stubDownloads();
  });

  afterEach(() => {
    downloads.restore();
  });

  it("test_usage_filters_by_product_and_level_go_to_the_url_the_api_and_the_csv", async () => {
    const recorder = record();
    const { user, router } = await renderUsage();
    expect(screen.queryByText(FILTERED)).not.toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole("combobox", { name: "Produto" })).toBeEnabled();
    });

    await pick(user, "Produto", "Suporte ERP");
    await pick(user, "Nível", "Suporte");

    await waitFor(() => {
      expect(last(recorder.reportQueries)).toMatchObject({
        group_by: "day",
        product_id: PRODUCT_ID,
        level: "support",
      });
    });
    expect(Object.fromEntries(new URLSearchParams(router.state.location.search))).toEqual({
      product: PRODUCT_ID,
      level: "support",
    });
    expect(screen.getByText(FILTERED)).toBeVisible();
    // Embeddings belong to no product or level: the table keeps only the chat columns.
    expect(headers("Uso por Dia")).toEqual([
      "Dia",
      "Tokens de entrada",
      "Tokens de saída",
      "Custo do chat",
      "Respostas",
      "Custo total",
    ]);

    await user.click(screen.getByRole("button", { name: "Exportar CSV" }));
    await waitFor(() => {
      expect(last(recorder.csvQueries)).toMatchObject({ product_id: PRODUCT_ID, level: "support" });
    });

    await pick(user, "Nível", "Todos os níveis");
    await pick(user, "Produto", "Todos os produtos");
    await waitFor(() => {
      expect(router.state.location.search).toBe("");
    });
  });

  it("test_usage_by_level_names_the_levels", async () => {
    record();
    await renderUsage(`${PATH}?group=level`, "Uso por Nível");

    const rows = within(screen.getByRole("table", { name: "Uso por Nível" })).getAllByRole("row");
    const names = rows.slice(1, -1).map((row) => within(row).getAllByRole("cell")[0]?.textContent);
    expect(names).toEqual(["Usuário final", "Suporte", "Desenvolvimento e produto"]);
  });

  it("test_usage_filters_are_off_when_grouping_by_source", async () => {
    const recorder = record();
    const { user, router } = await renderUsage(
      `${PATH}?group=source&level=support&product=${PRODUCT_ID}`,
      "Uso por Fonte",
    );

    expect(last(recorder.reportQueries)).not.toHaveProperty("level");
    expect(last(recorder.reportQueries)).not.toHaveProperty("product_id");
    for (const name of ["Produto", "Nível"]) {
      const select = screen.getByRole("combobox", { name });
      expect(select).toBeDisabled();
      expect(select).toHaveAccessibleDescription(CHAT_ONLY);
    }
    expect(screen.queryByText(FILTERED)).not.toBeInTheDocument();

    await pick(user, "Agrupar por", "Produto");
    await screen.findByRole("table", { name: "Uso por Produto" });
    expect(screen.getByRole("combobox", { name: "Nível" })).toBeEnabled();
    expect(screen.getByRole("combobox", { name: "Nível" })).toHaveTextContent("Todos os níveis");
    expect(router.state.location.search).toBe("?group=product");
  });

  it("test_usage_link_with_an_unlisted_product_keeps_it_selectable", async () => {
    const stranger = "00000000-0000-4000-8000-00000000beef";
    const recorder = record();
    await renderUsage(`${PATH}?group=model&product=${stranger}`, "Uso por Modelo");

    expect(last(recorder.reportQueries)).toMatchObject({ product_id: stranger });
    expect(screen.getByRole("combobox", { name: "Produto" })).toHaveTextContent(stranger);
  });

  it("test_usage_changing_the_period_keeps_the_filters", async () => {
    const recorder = record();
    const { user } = await renderUsage(`${PATH}?level=end_user`);

    await pick(user, "Período", "Mês passado");

    await waitFor(() => {
      expect(last(recorder.reportQueries)).toMatchObject({
        level: "end_user",
        from: "2026-09-01T00:00:00.000Z",
      });
    });
  });
});
