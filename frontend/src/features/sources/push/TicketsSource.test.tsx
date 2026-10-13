import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Role } from "@/lib/api/auth";
import { makeMe, makeWorkspace, WORKSPACE_ID } from "@/test/factories";
import { meAs, sourceStore, ticketActionFails, ticketStore } from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";
import {
  INGEST_TOKEN,
  makeTicketsSource,
  makeTicketUploadReport,
  TICKETS_SOURCE_ID,
} from "@/test/ticketFactories";

const PATH = `/w/${WORKSPACE_ID}/sources/${TICKETS_SOURCE_ID}`;

function setup(role: Role = "owner", source = makeTicketsSource()) {
  server.use(meAs(makeMe({ workspaces: [makeWorkspace({ role })] })));
  const sources = sourceStore([source], {
    testResults: {
      [TICKETS_SOURCE_ID]: {
        ok: false,
        error: {
          code: "source_unavailable",
          message: "No token.",
          details: { reason: "ingest_token_missing" },
        },
      },
    },
  });
  const tickets = ticketStore();
  server.use(...sources.handlers, ...tickets.handlers);
  return { sources, tickets };
}

async function renderSource(tab?: string) {
  renderWithProviders({ path: tab === undefined ? PATH : `${PATH}?tab=${tab}` });
  await screen.findByRole("heading", { level: 1, name: "suporte" });
}

describe("tickets source detail", () => {
  it("test_tickets_source_shows_how_it_indexes_and_viewer_sees_no_tabs", async () => {
    setup("viewer");
    await renderSource();

    expect(screen.getByText("Recebe chamados pela API e por upload de arquivo.")).toBeVisible();
    expect(screen.getByText("Anonimização ligada. Notas internas fora do índice.")).toBeVisible();
    expect(
      screen.getByText("Status indexados: Aberto, Pendente, Resolvido, Fechado"),
    ).toBeVisible();
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Execuções" })).toBeVisible();
  });

  it("test_tickets_source_summary_reads_other_settings", async () => {
    setup(
      "viewer",
      makeTicketsSource({
        config: { include_internal_notes: true, anonymize: false, statuses: ["closed"] },
      }),
    );
    await renderSource();

    expect(screen.getByText("Anonimização desligada. Notas internas indexadas.")).toBeVisible();
    expect(screen.getByText("Status indexados: Fechado")).toBeVisible();
  });

  it("test_tickets_source_test_connection_says_the_token_is_missing", async () => {
    const user = userEvent.setup();
    setup("editor");
    await renderSource();

    await user.click(screen.getByRole("button", { name: "Testar conexão" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "a fonte ainda não tem token de envio. Gere um na aba Integração.",
    );
  });

  it("test_tickets_source_editor_sees_examples_but_cannot_issue_the_token", async () => {
    const user = userEvent.setup();
    setup("editor");
    await renderSource();

    const tabs = screen.getByRole("tablist", { name: "Seções da fonte de chamados" });
    expect(
      within(tabs)
        .getAllByRole("tab")
        .map((tab) => tab.textContent),
    ).toEqual(["Integração", "Upload", "Prévia", "Indexação"]);
    expect(screen.queryByRole("button", { name: "Gerar token" })).not.toBeInTheDocument();
    expect(
      screen.getByText("Um owner ou admin do workspace gera o token desta fonte."),
    ).toBeVisible();
    const curl = screen.getByLabelText("Exemplo com curl");
    expect(curl).toHaveTextContent(`${window.location.origin}/v1/ingest/tickets`);
    expect(curl).toHaveTextContent("Bearer $KNOBRIDGE_INGEST_TOKEN");
    expect(screen.getByLabelText("Exemplo em Python")).toHaveTextContent(
      'TOKEN = os.environ["KNOBRIDGE_INGEST_TOKEN"]',
    );

    await user.click(screen.getByRole("button", { name: "Copiar exemplo Python" }));
    await expect(navigator.clipboard.readText()).resolves.toMatch(/^import json\n/);
  });

  it("test_tickets_source_owner_issues_the_token_once", async () => {
    const user = userEvent.setup();
    const { tickets } = setup("admin");
    await renderSource();

    await user.click(screen.getByRole("button", { name: "Gerar token" }));
    const confirm = await screen.findByRole("dialog", {
      name: "Gerar o token de envio de suporte?",
    });
    expect(within(confirm).getByText(/deixa de funcionar/)).toBeVisible();
    await user.click(within(confirm).getByRole("button", { name: "Gerar" }));

    const issued = await screen.findByRole("dialog", { name: "Token de envio gerado" });
    expect(within(issued).getByText(INGEST_TOKEN)).toBeVisible();
    expect(tickets.rotations).toEqual([TICKETS_SOURCE_ID]);
    await user.click(within(issued).getByRole("button", { name: "Copiar token" }));
    await expect(navigator.clipboard.readText()).resolves.toBe(INGEST_TOKEN);
    // The examples never carry the token.
    expect(screen.getByLabelText("Exemplo com curl")).not.toHaveTextContent(INGEST_TOKEN);

    await user.click(within(issued).getByRole("button", { name: "Concluir" }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expect(screen.queryByText(INGEST_TOKEN)).not.toBeInTheDocument();
    // Opening again starts over: the old token is gone for good.
    await user.click(screen.getByRole("button", { name: "Gerar token" }));
    expect(await screen.findByRole("dialog", { name: /Gerar o token/ })).toBeVisible();
    expect(screen.queryByText(INGEST_TOKEN)).not.toBeInTheDocument();
  });

  it("test_tickets_source_token_failure_is_shown_in_the_dialog", async () => {
    const user = userEvent.setup();
    setup();
    server.use(...ticketActionFails("token", 403, "forbidden"));
    await renderSource();

    await user.click(screen.getByRole("button", { name: "Gerar token" }));
    const confirm = await screen.findByRole("dialog");
    await user.click(within(confirm).getByRole("button", { name: "Gerar" }));

    expect(await within(confirm).findByRole("alert")).toHaveTextContent(
      "Você não tem permissão para fazer isso.",
    );
    await user.click(within(confirm).getByRole("button", { name: "Cancelar" }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });

  it("test_tickets_source_opens_the_tab_of_the_query_string", async () => {
    const user = userEvent.setup();
    setup();
    await renderSource("indexing");

    expect(screen.getByRole("tab", { name: "Indexação" })).toHaveAttribute("aria-selected", "true");
    expect(await screen.findByRole("heading", { name: "Execuções" })).toBeVisible();
    await user.click(screen.getByRole("tab", { name: "Prévia" }));
    expect(await screen.findByLabelText("Chamado (JSON)")).toBeVisible();
  });
});

describe("tickets upload", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("test_tickets_upload_shows_counts_and_errors_by_line", async () => {
    const user = userEvent.setup();
    const { tickets, sources } = setup("editor");
    await renderSource("upload");
    const reads = sources.reads.length;
    // Node's fetch cannot read jsdom's File (see `ticketStore`): check what the panel appended.
    const append = vi.spyOn(FormData.prototype, "append");

    const file = new File(['{"external_id":"A-1"}\n'], "export.jsonl", {
      type: "application/x-ndjson",
    });
    await user.upload(screen.getByLabelText("Arquivo"), file);
    await user.click(screen.getByRole("button", { name: "Enviar arquivo" }));

    const report = await screen.findByRole("region", { name: "Resultado do envio" });
    expect(within(report).getByRole("status")).toHaveTextContent(
      "6 itens lidos do arquivo JSONL. A indexação começou.",
    );
    expect(within(report).getByText("Na fila para indexar").nextElementSibling).toHaveTextContent(
      "2",
    );
    expect(within(report).getByText("Recusados").nextElementSibling).toHaveTextContent("3");
    const table = within(report).getByRole("table", { name: "Itens recusados do arquivo" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows.map((row) => within(row).getAllByRole("cell")[0]?.textContent)).toEqual([
      "2",
      "3",
      "4",
    ]);
    expect(rows[0]).toHaveTextContent("A-2");
    expect(rows[0]).toHaveTextContent("Fora do formato do chamado");
    expect(rows[0]).toHaveTextContent("status: enum");
    expect(rows[0]).toHaveTextContent("messages.0.created_at: missing");
    expect(rows[1]).toHaveTextContent("—");
    expect(rows[1]).toHaveTextContent("Linha que não é JSON válido");
    expect(rows[2]).toHaveTextContent("Chamado repetido no arquivo");
    expect(rows[2]).toHaveTextContent("Já apareceu na linha 1.");
    expect(tickets.uploads).toEqual([TICKETS_SOURCE_ID]);
    expect(append).toHaveBeenCalledWith("file", file, "export.jsonl");
    // The upload asked for a sync: the source is read again.
    await waitFor(() => {
      expect(sources.reads.length).toBeGreaterThan(reads);
    });
  });

  it("test_tickets_upload_of_json_shows_positions_and_truncation", async () => {
    const user = userEvent.setup();
    setup("editor");
    server.use(
      ...ticketStore({
        report: makeTicketUploadReport({
          format: "json",
          sync: "deferred",
          errors_truncated: true,
          errors: [
            {
              line: null,
              index: 0,
              external_id: "B-0",
              code: "duplicate_in_batch",
              message: "Duplicate.",
              details: { first_index: 0 },
            },
            {
              line: null,
              index: null,
              external_id: null,
              code: "future_code",
              message: "Mensagem do servidor.",
              details: null,
            },
          ],
        }),
      }).handlers,
    );
    await renderSource("upload");

    await user.upload(
      screen.getByLabelText("Arquivo"),
      new File(["[]"], "export.json", { type: "application/json" }),
    );
    await user.click(screen.getByRole("button", { name: "Enviar arquivo" }));

    const report = await screen.findByRole("region", { name: "Resultado do envio" });
    expect(within(report).getByRole("status")).toHaveTextContent(/arquivo JSON\. O serviço/);
    expect(within(report).getByText("Mostrando os primeiros 2 itens recusados.")).toBeVisible();
    const table = within(report).getByRole("table", { name: "Itens recusados do arquivo" });
    expect(within(table).getByRole("columnheader", { name: "Posição" })).toBeVisible();
    expect(within(table).getByText("Já apareceu na posição 0.")).toBeVisible();
    expect(within(table).getByText("Mensagem do servidor.")).toBeVisible();
  });

  it("test_tickets_upload_checks_the_file_before_sending", async () => {
    const user = userEvent.setup({ applyAccept: false });
    const { tickets } = setup("editor", makeTicketsSource({ active: false }));
    await renderSource("upload");

    expect(screen.getByText(/A fonte está desativada: o envio será recusado/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Enviar arquivo" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Escolha o arquivo a enviar.");

    await user.upload(screen.getByLabelText("Arquivo"), new File(["x"], "export.csv"));
    await user.click(screen.getByRole("button", { name: "Enviar arquivo" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Use um arquivo .json, .jsonl.");
    expect(tickets.uploads).toEqual([]);
  });

  it("test_tickets_upload_shows_a_whole_file_error", async () => {
    const user = userEvent.setup();
    setup("editor");
    server.use(...ticketActionFails("upload", 422, "upload_empty"));
    await renderSource("upload");

    await user.upload(screen.getByLabelText("Arquivo"), new File([""], "vazio.jsonl"));
    await user.click(screen.getByRole("button", { name: "Enviar arquivo" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("O arquivo não tem nenhum chamado.");
    expect(screen.queryByRole("region", { name: "Resultado do envio" })).not.toBeInTheDocument();
  });
});
