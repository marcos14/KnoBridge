import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Role } from "@/lib/api/auth";
import { makeMe, makeWorkspace, WORKSPACE_ID } from "@/test/factories";
import { meAs, sourceStore, ticketActionFails, ticketStore } from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";
import {
  CARDS_SOURCE_ID,
  INGEST_TOKEN,
  makeCardPreview,
  makeCardsSource,
  makeTicketsSummary,
  makeTicketUploadReport,
  SAMPLE_CARD,
} from "@/test/ticketFactories";

const PATH = `/w/${WORKSPACE_ID}/sources/${CARDS_SOURCE_ID}`;

function setup(role: Role = "owner", source = makeCardsSource()) {
  server.use(meAs(makeMe({ workspaces: [makeWorkspace({ role })] })));
  const sources = sourceStore([source]);
  const cards = ticketStore({
    summary: makeTicketsSummary({ failed: 2, last_received_at: "2026-10-10T11:00:00Z" }),
  });
  server.use(...sources.handlers, ...cards.handlers);
  return { sources, cards };
}

async function renderSource(tab?: string) {
  renderWithProviders({ path: tab === undefined ? PATH : `${PATH}?tab=${tab}` });
  await screen.findByRole("heading", { level: 1, name: "cards-dev" });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("cards source detail", () => {
  it("test_cards_source_shows_how_it_indexes_and_viewer_sees_no_tabs", async () => {
    setup("viewer");
    await renderSource();

    expect(screen.getByText(/Cards de desenvolvimento na coleção/)).toBeVisible();
    expect(
      screen.getByText("Recebe cards de desenvolvimento pela API e por upload de arquivo."),
    ).toBeVisible();
    expect(screen.getByText("Anonimização ligada. Comentários indexados.")).toBeVisible();
    expect(
      screen.getByText("Status indexados: Backlog, Em andamento, Concluído, Cancelado"),
    ).toBeVisible();
    expect(
      screen.getByText("Nível mínimo: Desenvolvimento e produto (padrão do tipo)"),
    ).toBeVisible();
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
  });

  it("test_cards_source_summary_reads_other_settings", async () => {
    setup(
      "viewer",
      makeCardsSource({
        config: { anonymize: false, include_comments: false, statuses: ["done"] },
      }),
    );
    await renderSource();

    expect(screen.getByText("Anonimização desligada. Comentários fora do índice.")).toBeVisible();
    expect(screen.getByText("Status indexados: Concluído")).toBeVisible();
  });

  it("test_cards_source_owner_sees_the_cards_integration_and_issues_the_token", async () => {
    const user = userEvent.setup();
    const { cards } = setup("owner");
    await renderSource();

    expect(screen.getByRole("tablist", { name: "Seções da fonte de cards" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Editar cards-dev" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Reindexar" })).toBeDisabled();
    expect(
      screen.getByText(/se identifica com este token em POST \/v1\/ingest\/cards/),
    ).toBeVisible();
    const curl = screen.getByLabelText("Exemplo com curl");
    expect(curl).toHaveTextContent(`${window.location.origin}/v1/ingest/cards`);
    expect(curl).toHaveTextContent('"card": {');
    expect(screen.getByLabelText("Exemplo em Python")).toHaveTextContent('"card": {');
    const inbox = await screen.findByRole("region", { name: "Situação da integração" });
    expect(
      await within(inbox).findByText(
        "2 cards falharam no último processamento e serão tentados de novo.",
      ),
    ).toBeVisible();
    expect(within(inbox).getByText(/Último card recebido em/)).toBeVisible();
    expect(within(inbox).getByLabelText("Cards recebidos por estado")).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Gerar token" }));
    const confirm = await screen.findByRole("dialog", {
      name: "Gerar o token de envio de cards-dev?",
    });
    await user.click(within(confirm).getByRole("button", { name: "Gerar" }));

    const issued = await screen.findByRole("dialog", { name: "Token de envio gerado" });
    expect(within(issued).getByText(INGEST_TOKEN)).toBeVisible();
    expect(cards.rotations).toEqual([CARDS_SOURCE_ID]);
  });

  it("test_cards_source_with_nothing_received_says_so", async () => {
    server.use(meAs(makeMe({ workspaces: [makeWorkspace({ role: "editor" })] })));
    server.use(...sourceStore([makeCardsSource()]).handlers, ...ticketStore().handlers);
    await renderSource();

    expect(await screen.findByText("Nenhum card recebido ainda.")).toBeVisible();
    expect(
      screen.getByText("Um owner ou admin do workspace gera o token desta fonte."),
    ).toBeVisible();
  });
});

describe("cards upload", () => {
  it("test_cards_upload_posts_to_the_cards_route_and_names_card_errors", async () => {
    const user = userEvent.setup();
    const { cards } = setup("editor");
    server.use(
      ...ticketStore({
        report: makeTicketUploadReport({
          sync: "pending",
          errors: [
            {
              line: 2,
              index: null,
              external_id: "C-1",
              code: "card_too_large",
              message: "Too large.",
              details: null,
            },
            {
              line: 3,
              index: null,
              external_id: "C-2",
              code: "validation_error",
              message: "Invalid.",
              details: [{ loc: ["sprint"], problem: "sprint_end_before_start" }],
            },
            {
              line: 4,
              index: null,
              external_id: "C-3",
              code: "future_code",
              message: "Mensagem do servidor.",
              details: null,
            },
          ],
        }),
      }).handlers,
    );
    await renderSource("upload");
    const append = vi.spyOn(FormData.prototype, "append");

    expect(screen.getByRole("heading", { name: "Enviar arquivo de cards" })).toBeVisible();
    const file = new File(['{"external_id":"C-1"}\n'], "cards.jsonl");
    await user.upload(screen.getByLabelText("Arquivo"), file);
    await user.click(screen.getByRole("button", { name: "Enviar arquivo" }));

    const report = await screen.findByRole("region", { name: "Resultado do envio" });
    expect(within(report).getByRole("status")).toHaveTextContent(
      "Já havia uma sincronização em andamento: os cards entram na próxima.",
    );
    const table = within(report).getByRole("table", { name: "Itens recusados do arquivo" });
    expect(within(table).getByRole("columnheader", { name: "Card" })).toBeVisible();
    expect(within(table).getByText("Card acima de 1 MiB")).toBeVisible();
    expect(within(table).getByText("Fora do formato do card")).toBeVisible();
    expect(within(table).getByText("sprint: sprint_end_before_start")).toBeVisible();
    expect(within(table).getByText("Mensagem do servidor.")).toBeVisible();
    expect(append).toHaveBeenCalledWith("file", file, "cards.jsonl");
    // The first store (from `setup`) was replaced; nothing went to it.
    expect(cards.uploads).toEqual([]);
  });

  it("test_cards_upload_records_the_cards_kind", async () => {
    const user = userEvent.setup();
    const { cards } = setup("editor");
    await renderSource("upload");

    await user.upload(screen.getByLabelText("Arquivo"), new File(["[]"], "cards.json"));
    await user.click(screen.getByRole("button", { name: "Enviar arquivo" }));

    await screen.findByRole("region", { name: "Resultado do envio" });
    expect(cards.uploadKinds).toEqual(["cards"]);
    expect(cards.uploads).toEqual([CARDS_SOURCE_ID]);
  });
});

describe("cards preview", () => {
  it("test_cards_preview_sends_the_card_and_shows_the_markdown", async () => {
    const user = userEvent.setup();
    const { cards } = setup("editor");
    await renderSource("preview");

    expect(screen.getByRole("heading", { name: "Prévia de um card" })).toBeVisible();
    await user.click(screen.getByLabelText("Card (JSON)"));
    await user.paste(JSON.stringify(SAMPLE_CARD));
    await user.click(screen.getByRole("button", { name: "Gerar prévia" }));

    const result = await screen.findByRole("region", {
      name: "Prévia: Permitir nota fiscal de exportação",
    });
    expect(within(result).getByText("Com anonimização. Comentários incluídos.")).toBeVisible();
    expect(within(result).getByLabelText("Markdown do card")).toHaveTextContent(
      "# Card PROJ-123: Permitir nota fiscal de exportação",
    );
    expect(within(result).getByText("[RESPONSAVEL_1] × 1")).toBeVisible();
    expect(cards.previews).toEqual([
      { sourceId: CARDS_SOURCE_ID, kind: "cards", body: { card: SAMPLE_CARD } },
    ]);
  });

  it("test_cards_preview_without_comments_says_so", async () => {
    const user = userEvent.setup();
    setup("editor");
    server.use(
      ...ticketStore({ cardPreview: makeCardPreview({ include_comments: false }) }).handlers,
    );
    await renderSource("preview");

    await user.click(screen.getByLabelText("Card (JSON)"));
    await user.paste(JSON.stringify(SAMPLE_CARD));
    await user.click(screen.getByRole("button", { name: "Gerar prévia" }));

    expect(await screen.findByText("Com anonimização. Comentários fora.")).toBeVisible();
  });

  it("test_cards_preview_refuses_what_is_not_a_card", async () => {
    const user = userEvent.setup();
    const { cards } = setup("editor");
    await renderSource("preview");

    await user.click(screen.getByRole("button", { name: "Gerar prévia" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Cole um card em JSON.");
    await user.click(screen.getByLabelText("Card (JSON)"));
    await user.paste("[1]");
    await user.click(screen.getByRole("button", { name: "Gerar prévia" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Cole um único card: um objeto JSON.",
    );
    expect(cards.previews).toEqual([]);
  });

  it("test_cards_preview_lists_the_problems_of_an_invalid_card", async () => {
    const user = userEvent.setup();
    setup("editor");
    server.use(
      ...ticketActionFails("preview", 422, "validation_error", [
        { loc: ["links", 0, "url"], problem: "link_url_required" },
      ]),
    );
    await renderSource("preview");

    await user.click(screen.getByLabelText("Card (JSON)"));
    await user.paste(JSON.stringify(SAMPLE_CARD));
    await user.click(screen.getByRole("button", { name: "Gerar prévia" }));

    const problems = await screen.findByRole("list", { name: "Problemas do card" });
    expect(problems).toHaveTextContent("links.0.url: link_url_required");
    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("Confira os dados informados.");
    });
  });
});
