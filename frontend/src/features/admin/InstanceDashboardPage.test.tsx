import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import {
  makeDegradedHealth,
  makeInstanceDashboard,
  makeInstanceHealth,
} from "@/test/dashboardFactories";
import { makeMe } from "@/test/factories";
import {
  instanceDashboardAs,
  instanceDashboardServerError,
  instanceHealthAs,
  instanceHealthServerError,
  meAs,
} from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

async function renderDashboard(path = "/admin") {
  server.use(meAs(makeMe({ is_superadmin: true })));
  const result = renderWithProviders({ path });
  await screen.findByRole("heading", { level: 1, name: "Painel da instância" });
  return result;
}

function healthOf(service: string): HTMLElement {
  const section = screen.getByRole("region", { name: "Saúde dos serviços" });
  const item = within(section)
    .getAllByRole("listitem")
    .find((element) => element.textContent.startsWith(service));
  if (item === undefined) {
    throw new Error(`No health item for ${service}`);
  }
  return item;
}

describe("InstanceDashboardPage", () => {
  it("test_instance_dashboard_is_the_admin_home_and_menu_item", async () => {
    await renderDashboard();

    const nav = screen.getByRole("navigation", { name: "Navegação principal" });
    const link = within(nav).getByRole("link", { name: "Painel" });
    expect(link).toHaveAttribute("href", "/admin");
    expect(link).toHaveAttribute("aria-current", "page");
    expect(within(nav).getByRole("link", { name: "Workspaces" })).not.toHaveAttribute(
      "aria-current",
    );
  });

  it("test_instance_dashboard_shows_counts", async () => {
    await renderDashboard();

    const counts = await screen.findByRole("region", { name: "Contagens da instância" });
    expect(counts).toHaveTextContent("Workspaces3");
    expect(counts).toHaveTextContent("2 ativos, 1 suspensos");
    expect(counts).toHaveTextContent("4 ativos em 30 dias, 1 suspensos, 1 superadmins");
    expect(counts).toHaveTextContent("Execuções com falha (7 dias)2");
    expect(counts).toHaveTextContent("Respostas com falha (7 dias)1");
  });

  it("test_instance_dashboard_lists_recent_failures", async () => {
    await renderDashboard();

    const table = await screen.findByRole("table", { name: "Execuções com falha mais recentes" });
    const rows = within(table).getAllByRole("row");
    expect(rows[1]).toHaveTextContent("Acme Suporte");
    expect(rows[1]).toHaveTextContent("erp-core");
    expect(rows[1]).toHaveTextContent("repository unreachable");
  });

  it("test_instance_dashboard_failure_without_error_or_end", async () => {
    const failures = makeInstanceDashboard().recent_failures.map((failure) => ({
      ...failure,
      error: null,
      finished_at: null,
    }));
    server.use(instanceDashboardAs(makeInstanceDashboard({ recent_failures: failures })));
    await renderDashboard();

    const table = await screen.findByRole("table", { name: "Execuções com falha mais recentes" });
    expect(within(table).getByText("Sem mensagem de erro")).toBeInTheDocument();
    expect(within(table).getByText("—")).toBeInTheDocument();
  });

  it("test_instance_dashboard_shows_usage_and_top_workspaces", async () => {
    await renderDashboard();

    const usage = await screen.findByRole("region", { name: "Uso" });
    expect(usage).toHaveTextContent("De 10 de set. de 2026 a 10 de out. de 2026");
    expect(usage).toHaveTextContent("Custo estimadoUS$ 2,75");
    expect(usage).toHaveTextContent("Tokens de embeddings1.250.000");
    expect(usage).toHaveTextContent("Tokens do chat (entrada + saída)110.000");
    expect(within(usage).queryByRole("note")).not.toBeInTheDocument();
    const rows = within(
      within(usage).getByRole("table", { name: "Custo por workspace" }),
    ).getAllByRole("row");
    expect(rows[1]).toHaveTextContent("Acme SuporteUS$ 2,501.000.000101.000");
    expect(rows[2]).toHaveTextContent("Beta Help");
  });

  it("test_instance_dashboard_warns_partial_usage_cost", async () => {
    const base = makeInstanceDashboard();
    server.use(
      instanceDashboardAs(
        makeInstanceDashboard({
          usage: { ...base.usage, unpriced_runs: 2, unpriced_answers: 3, by_workspace: [] },
        }),
      ),
    );
    await renderDashboard();

    const usage = await screen.findByRole("region", { name: "Uso" });
    expect(within(usage).getByRole("note")).toHaveTextContent(
      "Custo parcial: 2 execuções e 3 respostas usaram modelos sem preço conhecido.",
    );
    expect(within(usage).getByText("Nenhum uso no período.")).toBeInTheDocument();
  });

  it("test_instance_dashboard_shows_healthy_services", async () => {
    await renderDashboard();

    await screen.findByText("Versão 0.8.0");
    for (const service of ["API", "Banco de dados", "Temporal", "Worker"]) {
      expect(healthOf(service)).toHaveTextContent("Funcionando");
      expect(healthOf(service)).toHaveTextContent("Verificado agora");
    }
  });

  it("test_instance_dashboard_explains_degraded_services", async () => {
    server.use(instanceHealthAs(makeDegradedHealth()));
    await renderDashboard();

    await screen.findByText("Versão 0.8.0");
    expect(healthOf("Temporal")).toHaveTextContent("Com erro");
    expect(healthOf("Temporal")).toHaveTextContent("O Temporal não respondeu.");
    expect(healthOf("Worker")).toHaveTextContent("Desconhecido");
    expect(healthOf("Worker")).toHaveTextContent(
      "Sem o Temporal, não dá para saber se o worker está no ar.",
    );
  });

  it("test_instance_dashboard_shows_unknown_detail_as_sent", async () => {
    const health = makeInstanceHealth();
    server.use(
      instanceHealthAs({
        ...health,
        database: { ...health.database, status: "error", detail: "new detail" },
      }),
    );
    await renderDashboard();

    await screen.findByText("Versão 0.8.0");
    expect(healthOf("Banco de dados")).toHaveTextContent("new detail");
  });

  it("test_instance_dashboard_health_error_keeps_numbers", async () => {
    server.use(instanceHealthServerError);
    await renderDashboard();

    expect(await screen.findByText("Não foi possível verificar os serviços.")).toBeInTheDocument();
    expect(
      await screen.findByRole("region", { name: "Contagens da instância" }),
    ).toBeInTheDocument();
  });

  it("test_instance_dashboard_retries_after_load_error", async () => {
    const user = userEvent.setup();
    server.use(instanceDashboardServerError);
    await renderDashboard();

    expect(await screen.findByText("Não foi possível carregar o painel.")).toBeInTheDocument();
    server.use(instanceDashboardAs());
    await user.click(screen.getByRole("button", { name: "Tentar novamente" }));

    expect(
      await screen.findByRole("region", { name: "Contagens da instância" }),
    ).toBeInTheDocument();
  });
});
