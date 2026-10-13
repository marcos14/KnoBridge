import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { TicketsSummary } from "@/lib/api/tickets";
import { formatDateTime } from "@/lib/intl";
import { makeMe, makeWorkspace, WORKSPACE_ID } from "@/test/factories";
import { meAs, sourceStore, ticketStore, ticketsSummaryServerError } from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";
import {
  makeIngestToken,
  makeTicketsSource,
  makeTicketsSummary,
  TICKETS_SOURCE_ID,
} from "@/test/ticketFactories";

const PATH = `/w/${WORKSPACE_ID}/sources/${TICKETS_SOURCE_ID}?tab=integration`;
const TITLE = "Situação da integração";

function setup(summary?: TicketsSummary) {
  server.use(meAs(makeMe({ workspaces: [makeWorkspace({ role: "owner" })] })));
  const sources = sourceStore([makeTicketsSource()]);
  const tickets = ticketStore({ summary });
  server.use(...sources.handlers, ...tickets.handlers);
  return tickets;
}

async function renderIntegration() {
  const user = userEvent.setup();
  renderWithProviders({ path: PATH });
  return { user, section: await screen.findByRole("region", { name: TITLE }) };
}

function countOf(section: HTMLElement, label: string) {
  return within(section).getByText(label).nextElementSibling;
}

const when = (iso: string) => formatDateTime(new Date(iso), "pt-BR");

describe("tickets inbox summary", () => {
  it("test_inbox_summary_of_a_new_source_has_no_token_and_nothing_received", async () => {
    setup();
    const { section } = await renderIntegration();

    expect(await within(section).findByText("Nenhum token de envio gerado ainda.")).toBeVisible();
    for (const label of [
      "Aguardando processamento",
      "Indexados",
      "Fora dos status indexados",
      "Remoções aguardando",
      "Removidos",
    ]) {
      expect(countOf(section, label)).toHaveTextContent("0");
    }
    expect(within(section).getByText("Nenhum chamado recebido ainda.")).toBeVisible();
    expect(within(section).queryByText(/falh/)).not.toBeInTheDocument();
  });

  it("test_inbox_summary_shows_token_prefix_counts_failures_and_last_arrival", async () => {
    setup(
      makeTicketsSummary({
        counts: { pending: 3, indexed: 1250, filtered: 4, pending_delete: 1, deleted: 2 },
        failed: 2,
        last_received_at: "2026-10-11T15:30:00Z",
        token_prefix: "ab12cd34",
        token_created_at: "2026-10-10T12:00:00Z",
      }),
    );
    const { section } = await renderIntegration();

    expect(
      await within(section).findByText(
        `Token atual: kbi_ab12cd34_…, gerado em ${when("2026-10-10T12:00:00Z")}.`,
      ),
    ).toBeVisible();
    expect(countOf(section, "Aguardando processamento")).toHaveTextContent("3");
    expect(countOf(section, "Indexados")).toHaveTextContent("1.250");
    expect(countOf(section, "Fora dos status indexados")).toHaveTextContent("4");
    expect(countOf(section, "Remoções aguardando")).toHaveTextContent("1");
    expect(countOf(section, "Removidos")).toHaveTextContent("2");
    expect(
      within(section).getByText(
        "2 chamados falharam no último processamento e serão tentados de novo.",
      ),
    ).toBeVisible();
    expect(
      within(section).getByText(`Último chamado recebido em ${when("2026-10-11T15:30:00Z")}.`),
    ).toBeVisible();
  });

  it("test_inbox_summary_says_one_failure_in_the_singular", async () => {
    setup(
      makeTicketsSummary({ counts: { ...makeTicketsSummary().counts, pending: 1 }, failed: 1 }),
    );
    const { section } = await renderIntegration();

    expect(
      await within(section).findByText(
        "1 chamado falhou no último processamento e será tentado de novo.",
      ),
    ).toBeVisible();
  });

  it("test_inbox_summary_follows_a_new_token", async () => {
    const tickets = setup();
    const { user, section } = await renderIntegration();
    await within(section).findByText("Nenhum token de envio gerado ainda.");

    await user.click(screen.getByRole("button", { name: "Gerar token" }));
    const confirm = await screen.findByRole("dialog");
    await user.click(within(confirm).getByRole("button", { name: "Gerar" }));
    await screen.findByRole("dialog", { name: "Token de envio gerado" });

    const created = makeIngestToken().created_at;
    expect(
      await within(section).findByText(`Token atual: kbi_ab12cd34_…, gerado em ${when(created)}.`),
    ).toBeInTheDocument();
    expect(tickets.summaryReads()).toBe(2);
  });

  it("test_inbox_summary_failure_can_be_retried", async () => {
    setup();
    server.use(...ticketsSummaryServerError);
    const { user, section } = await renderIntegration();

    expect(await within(section).findByRole("alert")).toHaveTextContent(
      "Não foi possível carregar a situação da integração.",
    );
    server.resetHandlers();
    setup();
    await user.click(within(section).getByRole("button", { name: "Tentar novamente" }));

    await waitFor(() => {
      expect(within(section).getByText("Nenhum token de envio gerado ainda.")).toBeVisible();
    });
  });
});
