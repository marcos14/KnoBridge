import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { Role } from "@/lib/api/auth";
import {
  makeMe,
  makeNewRunner,
  makeRunnerSource,
  makeWorkspace,
  OTHER_RUNNER_ID,
  RUNNER_SOURCE_ID,
  WORKSPACE_ID,
} from "@/test/factories";
import {
  DISABLED_MODULE_ID,
  makeHarnessModule,
  makeHarnessModules,
  makeRunningHarnessJob,
  MODULE_ID,
  ROOT_MODULE_ID,
} from "@/test/harnessFactories";
import {
  harnessActionFails,
  harnessModulesServerError,
  harnessStore,
  meAs,
  runnersAs,
  sourceStore,
} from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

const PATH = `/w/${WORKSPACE_ID}/sources/${RUNNER_SOURCE_ID}`;
const MODULES = "Módulos da fonte";

type User = ReturnType<typeof userEvent.setup>;

function asRole(role: Role) {
  server.use(meAs(makeMe({ workspaces: [makeWorkspace({ role })] })));
}

function useStores(...args: Parameters<typeof harnessStore>) {
  const store = harnessStore(...args);
  server.use(...sourceStore([makeRunnerSource()]).handlers, ...store.handlers);
  return store;
}

async function renderModules(path = PATH) {
  const result = renderWithProviders({ path });
  await screen.findByRole("heading", { level: 1, name: "erp-local" });
  return result;
}

function rowOf(table: HTMLElement, title: string): HTMLElement {
  const row = within(table)
    .getAllByRole("row")
    .find((item) => within(item).queryByText(title, { exact: true }) !== null);
  if (row === undefined) {
    throw new Error(`No row for ${title}`);
  }
  return row;
}

async function fill(user: User, container: HTMLElement, label: string, value: string) {
  const input = within(container).getByLabelText(label);
  await user.clear(input);
  if (value !== "") {
    await user.paste(value);
  }
}

describe("ModulesTab list", () => {
  it("test_modules_tab_lists_modules_with_inventory_commit_and_last_job", async () => {
    useStores();
    await renderModules();

    const table = await screen.findByRole("table", { name: MODULES });
    expect(screen.getByRole("tab", { name: "Módulos" })).toHaveAttribute("aria-selected", "true");
    const root = rowOf(table, "(raiz)");
    expect(root).toHaveTextContent("Manual");
    expect(root).toHaveTextContent("*!*/**docs/**+1 padrão");
    expect(root).toHaveTextContent("3 arquivos · 120 linhas");
    expect(root).toHaveTextContent("Nunca rodou");
    const billing = rowOf(table, "src/faturamento");
    expect(billing).toHaveTextContent("Sugerido");
    expect(billing).toHaveTextContent("src-faturamento");
    expect(billing).toHaveTextContent("12 arquivos · 3.400 linhas");
    expect(within(billing).getByText("bbbbbbb")).toHaveAttribute("title", "b".repeat(40));
    expect(billing).toHaveTextContent("Concluída");
    const legacy = rowOf(table, "src/legado");
    expect(legacy).toHaveTextContent("40 arquivos · 51.000 linhas");
    expect(within(legacy).getByRole("checkbox", { name: "Selecionar src/legado" })).toBeDisabled();
    expect(within(legacy).getByRole("button", { name: "Ligar src/legado" })).toBeInTheDocument();
  });

  it("test_modules_tab_filters_by_title_key_or_pattern", async () => {
    const user = userEvent.setup();
    useStores();
    await renderModules();
    const table = await screen.findByRole("table", { name: MODULES });

    await user.type(screen.getByLabelText("Filtrar por título, chave ou padrão"), "legado");
    expect(within(table).getAllByRole("row")).toHaveLength(2);
    expect(rowOf(table, "src/legado")).toBeInTheDocument();

    await fill(user, document.body, "Filtrar por título, chave ou padrão", "nada-disso");
    expect(within(table).getByText("Nenhum módulo corresponde ao filtro.")).toBeInTheDocument();
  });

  it("test_modules_tab_viewer_reads_without_actions", async () => {
    asRole("viewer");
    useStores();
    await renderModules();

    const table = await screen.findByRole("table", { name: MODULES });
    expect(within(table).queryByRole("checkbox")).not.toBeInTheDocument();
    expect(within(table).queryByRole("button")).not.toBeInTheDocument();
    expect(rowOf(table, "src/legado")).toHaveTextContent("Desligado");
    expect(rowOf(table, "src/faturamento")).toHaveTextContent("Ligado");
    expect(screen.queryByRole("button", { name: "Novo módulo" })).not.toBeInTheDocument();
    expect(
      screen.queryByRole("region", { name: "Rodar módulos selecionados" }),
    ).not.toBeInTheDocument();
  });

  it("test_modules_tab_retries_after_load_failure", async () => {
    const user = userEvent.setup();
    server.use(...sourceStore([makeRunnerSource()]).handlers, harnessModulesServerError);
    await renderModules();

    expect(await screen.findByText("Não foi possível carregar os módulos.")).toHaveRole("alert");
    server.use(...harnessStore().handlers);
    await user.click(screen.getByRole("button", { name: "Tentar novamente" }));

    expect(await screen.findByRole("table", { name: MODULES })).toBeInTheDocument();
  });
});

describe("ModulesTab empty state", () => {
  it("test_modules_tab_empty_with_online_runner_says_it_waits_for_the_report", async () => {
    useStores([]);
    await renderModules();

    expect(await screen.findByText(/Nenhum módulo ainda/)).toBeInTheDocument();
    expect(await screen.findByText("O runner notebook-ana está online.")).toBeInTheDocument();
    expect(screen.queryByText("Como subir o runner")).not.toBeInTheDocument();
    expect(screen.queryByRole("table", { name: MODULES })).not.toBeInTheDocument();
  });

  it("test_modules_tab_empty_with_offline_runner_shows_how_to_bring_it_up", async () => {
    const user = userEvent.setup();
    const source = makeRunnerSource({
      config: { ...makeRunnerSource().config, runner_id: OTHER_RUNNER_ID },
    });
    server.use(
      ...sourceStore([source]).handlers,
      ...harnessStore([]).handlers,
      runnersAs([makeNewRunner()]),
    );
    await renderModules();

    expect(
      await screen.findByText(
        "O runner servidor-build está offline: as tarefas esperam na fila até ele voltar.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Como subir o runner" })).toBeInTheDocument();
    const commands = screen.getByLabelText("Comandos para subir o runner");
    expect(commands).toHaveTextContent(
      `knobridge-runner configure --server-url ${window.location.origin} --repo erp-core=/caminho/do/checkout`,
    );
    await user.click(screen.getByRole("button", { name: "Copiar comandos" }));

    expect(await screen.findByText("Copiado.")).toBeInTheDocument();
    await expect(navigator.clipboard.readText()).resolves.toMatch(/^uv tool install \.\/runner\n/);
  });

  it("test_modules_tab_empty_for_viewer_shows_the_commands_without_presence", async () => {
    asRole("viewer");
    useStores([]);
    await renderModules();

    expect(await screen.findByText("Como subir o runner")).toBeInTheDocument();
    expect(screen.queryByText(/O runner notebook-ana/)).not.toBeInTheDocument();
  });
});

describe("ModulesTab editing", () => {
  it("test_modules_tab_edit_module_makes_a_suggested_module_manual", async () => {
    const user = userEvent.setup();
    const store = useStores();
    await renderModules();
    const table = await screen.findByRole("table", { name: MODULES });

    await user.click(
      within(rowOf(table, "src/faturamento")).getByRole("button", {
        name: "Editar o módulo src/faturamento",
      }),
    );
    const dialog = await screen.findByRole("dialog", { name: "Editar módulo" });
    expect(within(dialog).getByText(/o torna manual/)).toBeInTheDocument();
    expect(within(dialog).queryByLabelText("Chave (opcional)")).not.toBeInTheDocument();
    expect(within(dialog).getByLabelText("Padrões")).toHaveValue("src/faturamento/**");
    await fill(user, dialog, "Título", "Faturamento");
    await fill(user, dialog, "Padrões", "src/faturamento/**\n\n!src/faturamento/testes/**\n");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await screen.findByText("Módulo Faturamento atualizado.")).toHaveRole("status");
    expect(store.changes).toEqual([
      {
        moduleId: MODULE_ID,
        body: {
          title: "Faturamento",
          paths: ["src/faturamento/**", "!src/faturamento/testes/**"],
          enabled: true,
        },
      },
    ]);
    expect(await within(table).findByText("Faturamento")).toBeInTheDocument();
    expect(rowOf(table, "Faturamento")).toHaveTextContent("Manual");
  });

  it("test_modules_tab_create_module_validates_then_saves", async () => {
    const user = userEvent.setup();
    const store = useStores();
    await renderModules();
    await screen.findByRole("table", { name: MODULES });

    await user.click(screen.getByRole("button", { name: "Novo módulo" }));
    const dialog = await screen.findByRole("dialog", { name: "Novo módulo" });
    await fill(user, dialog, "Chave (opcional)", "Chave Ruim");
    await fill(user, dialog, "Padrões", "../fora\nC:/abs");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await within(dialog).findByText("Informe o título.")).toBeInTheDocument();
    expect(within(dialog).getByText(/sem hífen nas pontas/)).toBeInTheDocument();
    expect(within(dialog).getByText(/relativo à raiz/)).toBeInTheDocument();
    expect(store.created).toEqual([]);

    await fill(user, dialog, "Título", "Relatórios fiscais");
    await fill(user, dialog, "Chave (opcional)", "");
    await fill(user, dialog, "Padrões", "src/relatorios/**");
    await user.click(within(dialog).getByRole("checkbox", { name: "Ligado" }));
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await screen.findByText("Módulo Relatórios fiscais criado.")).toBeInTheDocument();
    expect(store.created).toEqual([
      { title: "Relatórios fiscais", paths: ["src/relatorios/**"], enabled: false },
    ]);
    const table = screen.getByRole("table", { name: MODULES });
    expect(rowOf(table, "Relatórios fiscais")).toHaveTextContent("relatorios-fiscais");
  });

  it("test_modules_tab_create_module_with_taken_key_shows_the_error", async () => {
    const user = userEvent.setup();
    useStores();
    await renderModules();
    await screen.findByRole("table", { name: MODULES });

    await user.click(screen.getByRole("button", { name: "Novo módulo" }));
    const dialog = await screen.findByRole("dialog", { name: "Novo módulo" });
    await fill(user, dialog, "Título", "Outra raiz");
    await fill(user, dialog, "Chave (opcional)", "root");
    await fill(user, dialog, "Padrões", "*");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(
      await within(dialog).findByText("Já existe um módulo com essa chave nesta fonte."),
    ).toHaveRole("alert");
  });

  it("test_modules_tab_rejects_too_many_patterns", async () => {
    const user = userEvent.setup();
    useStores();
    await renderModules();
    await screen.findByRole("table", { name: MODULES });

    await user.click(screen.getByRole("button", { name: "Novo módulo" }));
    const dialog = await screen.findByRole("dialog", { name: "Novo módulo" });
    await fill(user, dialog, "Título", "Grande");
    await fill(
      user,
      dialog,
      "Padrões",
      Array.from({ length: 51 }, (_, index) => `p${String(index)}/**`).join("\n"),
    );
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await within(dialog).findByText("Use até 50 padrões.")).toBeInTheDocument();
  });

  it("test_modules_tab_switches_a_module_off_and_on", async () => {
    const user = userEvent.setup();
    const store = useStores();
    await renderModules();
    const table = await screen.findByRole("table", { name: MODULES });

    await user.click(screen.getByRole("button", { name: "Desligar src/faturamento" }));
    expect(
      await screen.findByText("Módulo src/faturamento desligado: ele não roda nem a cada commit."),
    ).toBeInTheDocument();
    await user.click(await within(table).findByRole("button", { name: "Ligar src/legado" }));

    expect(await screen.findByText("Módulo src/legado ligado.")).toBeInTheDocument();
    expect(store.changes).toEqual([
      { moduleId: MODULE_ID, body: { enabled: false } },
      { moduleId: DISABLED_MODULE_ID, body: { enabled: true } },
    ]);
  });

  it("test_modules_tab_switch_failure_shows_the_error", async () => {
    const user = userEvent.setup();
    useStores();
    server.use(harnessActionFails("updateModule", 404, "module_not_found"));
    await renderModules();
    await screen.findByRole("table", { name: MODULES });

    await user.click(screen.getByRole("button", { name: "Desligar src/faturamento" }));

    expect(await screen.findByText("Módulo não encontrado. A lista foi atualizada.")).toHaveRole(
      "alert",
    );
  });
});

describe("ModulesTab running", () => {
  it("test_modules_tab_runs_a_batch_with_the_chosen_executor_and_model", async () => {
    const user = userEvent.setup();
    const store = useStores(makeHarnessModules(), {
      jobs: [makeRunningHarnessJob()],
    });
    await renderModules();
    const table = await screen.findByRole("table", { name: MODULES });
    const bar = screen.getByRole("region", { name: "Rodar módulos selecionados" });
    expect(within(bar).getByRole("button", { name: "Rodar módulos" })).toBeDisabled();

    await user.click(within(table).getByRole("checkbox", { name: "Selecionar (raiz)" }));
    await user.click(within(table).getByRole("checkbox", { name: "Selecionar src/faturamento" }));
    expect(screen.getByText("2 módulos selecionados")).toBeInTheDocument();
    await user.click(within(bar).getByRole("combobox", { name: "Executor" }));
    expect(screen.getByRole("option", { name: "Padrão da fonte (Codex)" })).toBeInTheDocument();
    await user.click(screen.getByRole("option", { name: "Claude Code" }));
    await user.type(within(bar).getByLabelText("Modelo (opcional)"), "modelo x");
    expect(within(bar).getByText(/Use até 100 caracteres/)).toBeInTheDocument();
    expect(within(bar).getByRole("button", { name: "Rodar 2 módulos" })).toBeDisabled();
    await fill(user, bar, "Modelo (opcional)", "claude-opus-4-1");
    await user.click(within(bar).getByRole("button", { name: "Rodar 2 módulos" }));

    const result = await within(bar).findByRole("status");
    expect(result).toHaveTextContent("1 tarefa na fila.");
    expect(result).toHaveTextContent("1 módulo pulado:");
    expect(result).toHaveTextContent("(raiz): já tem tarefa na fila ou em execução");
    expect(store.enqueued).toEqual([
      {
        module_ids: [ROOT_MODULE_ID, MODULE_ID],
        executor: "claude_code",
        model: "claude-opus-4-1",
      },
    ]);
    expect(screen.getByText("Nenhum módulo selecionado")).toBeInTheDocument();
    expect(await within(rowOf(table, "src/faturamento")).findByText("Na fila")).toBeVisible();
  });

  it("test_modules_tab_runs_with_the_source_defaults_and_lists_skipped_reasons", async () => {
    const user = userEvent.setup();
    const store = useStores(makeHarnessModules(), {
      forceSkip: { [MODULE_ID]: "module_disabled", [ROOT_MODULE_ID]: "unknown_reason" },
    });
    await renderModules();
    await screen.findByRole("table", { name: MODULES });

    await user.click(screen.getByRole("button", { name: "Selecionar os ligados do filtro" }));
    expect(screen.getByText("2 módulos selecionados")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Rodar 2 módulos" }));

    const bar = screen.getByRole("region", { name: "Rodar módulos selecionados" });
    const status = await within(bar).findByRole("status");
    expect(status).toHaveTextContent("Nenhuma tarefa na fila.");
    expect(status).toHaveTextContent("2 módulos pulados:");
    expect(status).toHaveTextContent("src/faturamento: está desligado");
    expect(status).toHaveTextContent("(raiz): unknown_reason");
    expect(store.enqueued).toEqual([{ module_ids: [ROOT_MODULE_ID, MODULE_ID] }]);
  });

  it("test_modules_tab_clear_selection_empties_the_batch", async () => {
    const user = userEvent.setup();
    useStores();
    await renderModules();
    await screen.findByRole("table", { name: MODULES });

    await user.click(screen.getByRole("button", { name: "Selecionar os ligados do filtro" }));
    await user.click(screen.getByRole("checkbox", { name: "Selecionar (raiz)" }));
    expect(screen.getByText("1 módulo selecionado")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Limpar seleção" }));

    expect(screen.getByText("Nenhum módulo selecionado")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Limpar seleção" })).toBeDisabled();
  });

  it("test_modules_tab_run_on_inactive_source_explains_it", async () => {
    const user = userEvent.setup();
    useStores([makeHarnessModule()]);
    server.use(harnessActionFails("enqueue", 409, "source_inactive"));
    await renderModules();
    await screen.findByRole("table", { name: MODULES });

    await user.click(screen.getByRole("checkbox", { name: "Selecionar src/faturamento" }));
    await user.click(screen.getByRole("button", { name: "Rodar 1 módulo" }));

    expect(
      await screen.findByText("A fonte está desativada. Ative-a para rodar módulos."),
    ).toHaveRole("alert");
  });

  it("test_modules_tab_run_failure_shows_the_api_error", async () => {
    const user = userEvent.setup();
    useStores([makeHarnessModule()]);
    server.use(harnessActionFails("enqueue", 404, "module_not_found"));
    await renderModules();
    await screen.findByRole("table", { name: MODULES });

    await user.click(screen.getByRole("checkbox", { name: "Selecionar src/faturamento" }));
    await user.click(screen.getByRole("button", { name: "Rodar 1 módulo" }));

    expect(await screen.findByText("Módulo não encontrado. A lista foi atualizada.")).toHaveRole(
      "alert",
    );
  });
});

describe("RunnerSourceTabs", () => {
  it("test_runner_source_tabs_follow_the_query_string", async () => {
    const user = userEvent.setup();
    useStores();
    const { router } = await renderModules(`${PATH}?tab=jobs`);

    expect(await screen.findByRole("tab", { name: "Tarefas" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await user.click(screen.getByRole("tab", { name: "Indexação" }));

    expect(await screen.findByRole("table", { name: "Execuções da fonte" })).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Documentos da fonte" })).toBeInTheDocument();
    expect(router.state.location.search).toBe("?tab=indexing");
  });
});
