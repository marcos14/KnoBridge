import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { WORKSPACE_ID } from "@/test/factories";
import { sourceStore, ticketActionFails, ticketStore } from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";
import {
  makeTicketPreview,
  makeTicketsSource,
  SAMPLE_TICKET,
  TICKETS_SOURCE_ID,
} from "@/test/ticketFactories";

type User = ReturnType<typeof userEvent.setup>;

function setup(options: Parameters<typeof ticketStore>[0] = {}) {
  const tickets = ticketStore(options);
  server.use(...sourceStore([makeTicketsSource()]).handlers, ...tickets.handlers);
  return tickets;
}

async function renderPreview() {
  renderWithProviders({ path: `/w/${WORKSPACE_ID}/sources/${TICKETS_SOURCE_ID}?tab=preview` });
  return screen.findByLabelText("Chamado (JSON)");
}

async function previewOf(user: User, text: string) {
  const field = await renderPreview();
  if (text !== "") {
    await user.click(field);
    await user.paste(text);
  }
  await user.click(screen.getByRole("button", { name: "Gerar prévia" }));
}

describe("tickets preview", () => {
  it("test_tickets_preview_shows_markdown_and_markers", async () => {
    const user = userEvent.setup();
    const tickets = setup();

    await previewOf(user, JSON.stringify(SAMPLE_TICKET));

    const result = await screen.findByRole("region", {
      name: "Prévia: Erro 4021 ao fechar o caixa",
    });
    expect(within(result).getByText("Com anonimização. Notas internas fora.")).toBeVisible();
    const markers = within(result).getByRole("list", { name: "Marcadores aplicados" });
    expect(
      within(markers)
        .getAllByRole("listitem")
        .map((item) => item.textContent),
    ).toEqual(["[TELEFONE] × 1", "[SOLICITANTE] × 2"]);
    expect(within(result).getByLabelText("Markdown do chamado")).toHaveTextContent(
      "# Chamado 48213: Erro 4021 ao fechar o caixa",
    );
    expect(tickets.previews).toEqual([
      { sourceId: TICKETS_SOURCE_ID, kind: "tickets", body: { ticket: SAMPLE_TICKET } },
    ]);
  });

  it("test_tickets_preview_without_anonymization_hides_the_markers", async () => {
    const user = userEvent.setup();
    setup({
      preview: makeTicketPreview({ anonymize: false, include_internal_notes: true, markers: [] }),
    });

    await previewOf(user, JSON.stringify(SAMPLE_TICKET));

    const result = await screen.findByRole("region", { name: /^Prévia:/ });
    expect(within(result).getByText("Sem anonimização. Notas internas incluídas.")).toBeVisible();
    expect(within(result).queryByText("Marcadores aplicados")).not.toBeInTheDocument();
  });

  it("test_tickets_preview_says_when_no_marker_was_applied", async () => {
    const user = userEvent.setup();
    setup({ preview: makeTicketPreview({ markers: [] }) });

    await previewOf(user, JSON.stringify(SAMPLE_TICKET));

    expect(await screen.findByText("Nenhum dado pessoal encontrado pelas regras.")).toBeVisible();
  });

  it.each([
    ["", "Cole um chamado em JSON."],
    ["{ não é json", "O texto não é um JSON válido."],
    ["[1, 2]", "Cole um único chamado: um objeto JSON."],
  ])("test_tickets_preview_refuses_%j_before_sending", async (text, message) => {
    const user = userEvent.setup();
    const tickets = setup();

    await previewOf(user, text);

    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(tickets.previews).toEqual([]);
  });

  it("test_tickets_preview_lists_the_problems_of_an_invalid_ticket", async () => {
    const user = userEvent.setup();
    setup();
    server.use(
      ...ticketActionFails("preview", 422, "validation_error", [
        { loc: ["title"], problem: "string_too_short" },
        { loc: [], problem: "model_type" },
      ]),
    );

    await previewOf(user, JSON.stringify({ ...SAMPLE_TICKET, title: "" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Confira os dados informados.");
    const problems = screen.getByRole("list", { name: "Problemas do chamado" });
    expect(
      within(problems)
        .getAllByRole("listitem")
        .map((item) => item.textContent),
    ).toEqual(["title: string_too_short", "model_type"]);
    expect(screen.queryByRole("region", { name: /^Prévia:/ })).not.toBeInTheDocument();
  });

  it("test_tickets_preview_shows_a_ticket_too_large_error", async () => {
    const user = userEvent.setup();
    setup();
    server.use(...ticketActionFails("preview", 422, "ticket_too_large", { max_bytes: 1048576 }));

    await previewOf(user, JSON.stringify(SAMPLE_TICKET));

    expect(await screen.findByRole("alert")).toHaveTextContent("O chamado passa de 1 MiB.");
    expect(screen.queryByRole("list", { name: "Problemas do chamado" })).not.toBeInTheDocument();
  });
});
