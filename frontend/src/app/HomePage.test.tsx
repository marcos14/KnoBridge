import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { Role } from "@/lib/api/auth";
import { makeChecklist, makeWorkspaceDashboard } from "@/test/dashboardFactories";
import { makeMe, makeWorkspace, WORKSPACE_ID } from "@/test/factories";
import {
  meAs,
  workspaceDashboardAs,
  workspaceDashboardPending,
  workspaceDashboardServerError,
} from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

const ALL_DONE = makeChecklist(["provider", "collection", "source", "assistant", "chat"]);

function asRole(role: Role) {
  server.use(meAs(makeMe({ workspaces: [makeWorkspace({ role })] })));
}

async function renderHome() {
  const result = renderWithProviders({ path: `/w/${WORKSPACE_ID}` });
  await screen.findByRole("heading", { level: 1, name: "Início" });
  return result;
}

function card(label: string): HTMLElement {
  const term = within(screen.getByRole("region", { name: "Números do workspace" })).getByText(
    label,
  );
  const item = term.parentElement;
  if (item === null) {
    throw new Error(`No card for ${label}`);
  }
  return item;
}

describe("HomePage", () => {
  it("test_home_page_redirects_root_to_workspace_home", async () => {
    const { router } = renderWithProviders({ path: "/" });

    expect(await screen.findByRole("heading", { level: 1, name: "Início" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe(`/w/${WORKSPACE_ID}`);
    expect(screen.getByText("Resumo de Acme Suporte.")).toBeInTheDocument();
  });

  it("test_home_page_shows_dashboard_cards_with_cost_for_owner", async () => {
    await renderHome();

    await screen.findByRole("region", { name: "Números do workspace" });
    expect(card("Documentos indexados")).toHaveTextContent("1.234");
    expect(card("Fontes ativas")).toHaveTextContent("2 de 3");
    expect(card("Execuções com falha (7 dias)")).toHaveTextContent("1");
    expect(card("Conversas no mês")).toHaveTextContent("12");
    expect(card("Avaliações positivas no mês")).toHaveTextContent("8");
    expect(card("Avaliações negativas no mês")).toHaveTextContent("2");
    expect(card("Custo estimado no mês")).toHaveTextContent("US$ 1,50");
    expect(card("Custo estimado no mês")).toHaveTextContent("Embeddings US$ 0,25, chat US$ 1,25");
    expect(
      screen.getByText("Números do mês contados desde 1 de out. de 2026."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
  });

  it("test_home_page_hides_cost_card_without_cost_month", async () => {
    asRole("viewer");
    server.use(workspaceDashboardAs(makeWorkspaceDashboard({ cost_month: null })));
    await renderHome();

    await screen.findByRole("region", { name: "Números do workspace" });
    expect(screen.queryByText("Custo estimado no mês")).not.toBeInTheDocument();
  });

  it("test_home_page_warns_partial_cost", async () => {
    server.use(
      workspaceDashboardAs(
        makeWorkspaceDashboard({
          cost_month: { embedding_cost_usd: 0, chat_cost_usd: 0.5, cost_usd: 0.5, partial: true },
        }),
      ),
    );
    await renderHome();

    expect(await screen.findByRole("note")).toHaveTextContent(
      "Custo parcial: há execuções ou respostas com modelo sem preço conhecido.",
    );
  });

  it("test_home_page_checklist_lists_pending_steps_with_links", async () => {
    const user = userEvent.setup();
    const { router } = await renderHome();

    const checklist = await screen.findByRole("region", { name: "Primeiros passos" });
    expect(within(checklist).getByText("2 de 5 concluídos", { exact: false })).toBeInTheDocument();
    expect(within(checklist).queryByText("Cadastre um provedor de LLM")).not.toBeInTheDocument();
    expect(within(checklist).queryByText("Crie uma coleção")).not.toBeInTheDocument();
    expect(within(checklist).getAllByRole("listitem")).toHaveLength(3);
    expect(within(checklist).getByRole("link", { name: "Ir para o Chat" })).toHaveAttribute(
      "href",
      `/w/${WORKSPACE_ID}/chat`,
    );

    await user.click(within(checklist).getByRole("link", { name: "Ir para Fontes" }));

    expect(router.state.location.pathname).toBe(`/w/${WORKSPACE_ID}/sources`);
  });

  it("test_home_page_checklist_tells_viewer_to_ask_an_admin", async () => {
    asRole("viewer");
    server.use(workspaceDashboardAs(makeWorkspaceDashboard({ checklist: makeChecklist() })));
    await renderHome();

    const checklist = await screen.findByRole("region", { name: "Primeiros passos" });
    expect(
      within(checklist).getAllByText("Peça a um administrador do workspace para fazer este passo."),
    ).toHaveLength(4);
    expect(within(checklist).getAllByRole("link")).toHaveLength(1);
    expect(within(checklist).getByRole("link", { name: "Ir para o Chat" })).toBeInTheDocument();
  });

  it("test_home_page_hides_checklist_when_every_step_is_done", async () => {
    server.use(workspaceDashboardAs(makeWorkspaceDashboard({ checklist: ALL_DONE })));
    await renderHome();

    await screen.findByRole("region", { name: "Números do workspace" });
    expect(screen.queryByRole("region", { name: "Primeiros passos" })).not.toBeInTheDocument();
  });

  it("test_home_page_shows_loading_state", async () => {
    server.use(workspaceDashboardPending);
    await renderHome();

    expect(await screen.findByText("Carregando o painel…")).toBeInTheDocument();
  });

  it("test_home_page_retries_after_load_error", async () => {
    const user = userEvent.setup();
    server.use(workspaceDashboardServerError);
    await renderHome();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não foi possível carregar o painel.",
    );
    server.use(workspaceDashboardAs());
    await user.click(screen.getByRole("button", { name: "Tentar novamente" }));

    expect(await screen.findByRole("region", { name: "Números do workspace" })).toBeInTheDocument();
  });
});
