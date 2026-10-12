import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import {
  COLLECTION_ID,
  makeRunner,
  makeRunnerSource,
  OTHER_RUNNER_ID,
  REVOKED_RUNNER_ID,
  RUNNER_ID,
  RUNNER_SOURCE_ID,
  WORKSPACE_ID,
} from "@/test/factories";
import { runnersAs, runnersServerError, sourceActionFails, sourceStore } from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

const PATH = `/w/${WORKSPACE_ID}/sources`;

type User = ReturnType<typeof userEvent.setup>;

async function openRunnerCreate(user: User) {
  renderWithProviders({ path: PATH });
  await screen.findByRole("table", { name: "Fontes do workspace" });
  await user.click(screen.getByRole("button", { name: "Nova fonte" }));
  const dialog = await screen.findByRole("dialog", { name: "Nova fonte" });
  await user.click(within(dialog).getByRole("radio", { name: "Runner local" }));
  return dialog;
}

async function choose(user: User, dialog: HTMLElement, field: string, option: string) {
  await user.click(within(dialog).getByRole("combobox", { name: field }));
  await user.click(await screen.findByRole("option", { name: option }));
}

async function save(user: User, dialog: HTMLElement) {
  await user.click(within(dialog).getByRole("button", { name: "Salvar" }));
}

async function fill(user: User, dialog: HTMLElement, label: string, value: string) {
  const input = within(dialog).getByLabelText(label);
  await user.clear(input);
  await user.paste(value);
}

describe("runner source create", () => {
  it("test_create_runner_source_picks_runner_and_served_repository", async () => {
    const user = userEvent.setup();
    const store = sourceStore([]);
    server.use(...store.handlers);
    const dialog = await openRunnerCreate(user);

    expect(within(dialog).queryByLabelText("Caminho do clone")).not.toBeInTheDocument();
    await user.click(within(dialog).getByRole("combobox", { name: "Runner" }));
    const options = await screen.findAllByRole("option");
    expect(options.map((item) => item.textContent)).toEqual([
      "notebook-ana",
      "servidor-build (offline)",
    ]);
    await user.click(screen.getByRole("option", { name: "notebook-ana" }));
    await choose(user, dialog, "Repositório", "portal");
    await fill(user, dialog, "Nome", "portal-local");
    await save(user, dialog);

    await screen.findByText(/Fonte portal-local criada/);
    expect(store.created).toEqual([
      {
        collection_id: COLLECTION_ID,
        kind: "runner",
        name: "portal-local",
        config: {
          runner_id: RUNNER_ID,
          repository: "portal",
          default_executor: "claude_code",
          models: { claude_code: null, codex: null },
          budget_usd: 5,
          timeout_seconds: 1200,
          auto_on_commit: false,
          excerpt_max_lines: 30,
        },
        include_globs: [],
        exclude_globs: [],
        schedule_cron: null,
        schedule_enabled: false,
        active: true,
      },
    ]);
  });

  it("test_create_runner_source_validates_the_runner_fields", async () => {
    const user = userEvent.setup();
    const store = sourceStore([]);
    server.use(...store.handlers);
    const dialog = await openRunnerCreate(user);

    await fill(user, dialog, "Nome", "erp-local");
    await fill(user, dialog, "Modelo do Claude Code (opcional)", "modelo x");
    await fill(user, dialog, "Orçamento por tarefa (US$)", "0");
    await fill(user, dialog, "Tempo limite por tarefa (segundos)", "30");
    await fill(user, dialog, "Linhas de excerto por evidência", "81");
    await save(user, dialog);

    expect(await within(dialog).findByText("Escolha um runner.")).toBeInTheDocument();
    expect(within(dialog).getByText("Informe o repositório.")).toBeInTheDocument();
    expect(
      within(dialog).getByText("Use até 100 caracteres entre letras, números e . _ : / -"),
    ).toBeInTheDocument();
    expect(within(dialog).getByText("Informe um valor de 0,1 a 100.")).toBeInTheDocument();
    expect(within(dialog).getByText("Informe um número inteiro de 60 a 7200.")).toBeInTheDocument();
    expect(within(dialog).getByText("Informe um número inteiro de 0 a 80.")).toBeInTheDocument();
    expect(store.created).toEqual([]);
  });

  it("test_create_runner_source_types_the_repository_of_an_offline_runner", async () => {
    const user = userEvent.setup();
    const store = sourceStore([]);
    server.use(...store.handlers);
    const dialog = await openRunnerCreate(user);

    await choose(user, dialog, "Runner", "servidor-build (offline)");
    expect(
      within(dialog).getByText(/está offline ou ainda não informou repositórios/),
    ).toBeInTheDocument();
    await fill(user, dialog, "Nome", "build");
    await fill(user, dialog, "Repositório", "../erp");
    await save(user, dialog);

    expect(await within(dialog).findByText(/nunca um caminho/)).toBeInTheDocument();
    await fill(user, dialog, "Repositório", "erp-build");
    await save(user, dialog);

    await screen.findByText(/Fonte build criada/);
    expect(store.created[0]?.config).toMatchObject({
      runner_id: OTHER_RUNNER_ID,
      repository: "erp-build",
      default_executor: "claude_code",
      budget_usd: 5,
      timeout_seconds: 1200,
      excerpt_max_lines: 30,
      auto_on_commit: false,
    });
  });

  it("test_create_runner_source_repository_in_use_shows_the_error", async () => {
    const user = userEvent.setup();
    server.use(sourceActionFails("create", 409, "runner_repository_in_use"));
    const dialog = await openRunnerCreate(user);

    await choose(user, dialog, "Runner", "notebook-ana");
    await choose(user, dialog, "Repositório", "erp-core");
    await fill(user, dialog, "Nome", "erp-de-novo");
    await save(user, dialog);

    expect(
      await within(dialog).findByText("Já existe uma fonte para esse repositório nesse runner."),
    ).toBeVisible();
  });

  it("test_create_runner_source_without_runners_explains_who_registers_them", async () => {
    const user = userEvent.setup();
    server.use(runnersAs([makeRunner({ revoked_at: "2026-10-09T00:00:00Z" })]));
    const dialog = await openRunnerCreate(user);

    expect(
      await within(dialog).findByText(
        "Nenhum runner disponível. Um owner ou admin cadastra em Runners.",
      ),
    ).toHaveRole("alert");
    expect(within(dialog).queryByRole("combobox", { name: "Runner" })).not.toBeInTheDocument();
  });

  it("test_create_runner_source_when_runners_fail_to_load", async () => {
    const user = userEvent.setup();
    server.use(runnersServerError);
    const dialog = await openRunnerCreate(user);

    expect(await within(dialog).findByText("Não foi possível carregar os runners.")).toHaveRole(
      "alert",
    );
    expect(within(dialog).getByLabelText("Repositório")).toBeInTheDocument();
  });
});

describe("runner source edit and detail", () => {
  it("test_edit_runner_source_keeps_its_values_and_unreported_repository", async () => {
    const user = userEvent.setup();
    const source = makeRunnerSource({
      config: { ...makeRunnerSource().config, repository: "legado" },
    });
    const store = sourceStore([source]);
    server.use(...store.handlers);
    renderWithProviders({ path: `${PATH}/${RUNNER_SOURCE_ID}` });

    expect(await screen.findByText("Repositório: legado")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Editar erp-local" }));
    const dialog = await screen.findByRole("dialog", { name: "Editar fonte" });
    expect(within(dialog).getByRole("radio", { name: "Runner local" })).toBeChecked();
    expect(await within(dialog).findByRole("combobox", { name: "Runner" })).toHaveTextContent(
      "notebook-ana",
    );
    expect(within(dialog).getByRole("combobox", { name: "Repositório" })).toHaveTextContent(
      "legado",
    );
    expect(within(dialog).getByRole("radio", { name: "Codex" })).toBeChecked();
    expect(within(dialog).getByLabelText("Modelo do Claude Code (opcional)")).toHaveValue(
      "claude-sonnet-4-5",
    );
    expect(within(dialog).getByLabelText("Orçamento por tarefa (US$)")).toHaveValue("2.5");
    expect(
      within(dialog).getByRole("checkbox", { name: "Gerar conhecimento a cada commit" }),
    ).toBeChecked();
    await save(user, dialog);

    await screen.findByText("Fonte erp-local atualizada.");
    expect(store.changes[0]?.body.config).toEqual({
      runner_id: RUNNER_ID,
      repository: "legado",
      default_executor: "codex",
      models: { claude_code: "claude-sonnet-4-5", codex: null },
      budget_usd: 2.5,
      timeout_seconds: 900,
      auto_on_commit: true,
      excerpt_max_lines: 20,
    });
  });

  it("test_edit_runner_source_changes_how_the_harness_runs", async () => {
    const user = userEvent.setup();
    const store = sourceStore([makeRunnerSource()]);
    server.use(...store.handlers);
    renderWithProviders({ path: `${PATH}/${RUNNER_SOURCE_ID}` });

    await user.click(await screen.findByRole("button", { name: "Editar erp-local" }));
    const dialog = await screen.findByRole("dialog", { name: "Editar fonte" });
    await user.click(within(dialog).getByRole("radio", { name: "Claude Code" }));
    await user.clear(within(dialog).getByLabelText("Modelo do Claude Code (opcional)"));
    await fill(user, dialog, "Modelo do Codex (opcional)", "gpt-5-codex");
    await fill(user, dialog, "Orçamento por tarefa (US$)", "7,5");
    await fill(user, dialog, "Tempo limite por tarefa (segundos)", "600");
    await fill(user, dialog, "Linhas de excerto por evidência", "0");
    await user.click(
      within(dialog).getByRole("checkbox", { name: "Gerar conhecimento a cada commit" }),
    );
    await save(user, dialog);

    await screen.findByText("Fonte erp-local atualizada.");
    expect(store.changes[0]?.body.config).toEqual({
      runner_id: RUNNER_ID,
      repository: "erp-core",
      default_executor: "claude_code",
      models: { claude_code: null, codex: "gpt-5-codex" },
      budget_usd: 7.5,
      timeout_seconds: 600,
      auto_on_commit: false,
      excerpt_max_lines: 0,
    });
  });

  it("test_edit_runner_source_on_a_revoked_runner_keeps_it_selectable", async () => {
    const user = userEvent.setup();
    const source = makeRunnerSource({
      config: { ...makeRunnerSource().config, runner_id: REVOKED_RUNNER_ID },
    });
    server.use(...sourceStore([source]).handlers);
    renderWithProviders({ path: `${PATH}/${RUNNER_SOURCE_ID}` });

    await user.click(await screen.findByRole("button", { name: "Editar erp-local" }));
    const dialog = await screen.findByRole("dialog", { name: "Editar fonte" });

    expect(await within(dialog).findByRole("combobox", { name: "Runner" })).toHaveTextContent(
      "antigo (revogado)",
    );
    expect(within(dialog).getByLabelText("Repositório")).toHaveValue("erp-core");
  });

  it("test_runner_source_test_explains_why_the_runner_is_unreachable", async () => {
    const user = userEvent.setup();
    const store = sourceStore([makeRunnerSource()], {
      testResults: {
        [RUNNER_SOURCE_ID]: {
          ok: false,
          error: {
            code: "source_unavailable",
            message: "Runner offline.",
            details: { reason: "runner_offline" },
          },
        },
      },
    });
    server.use(...store.handlers);
    renderWithProviders({ path: `${PATH}/${RUNNER_SOURCE_ID}` });

    await user.click(await screen.findByRole("button", { name: "Testar conexão" }));

    expect(
      await screen.findByText("A fonte erp-local não respondeu: o runner está offline"),
    ).toBeInTheDocument();
  });

  it("test_runner_source_appears_in_the_list_with_its_repository", async () => {
    server.use(...sourceStore([makeRunnerSource()]).handlers);
    renderWithProviders({ path: PATH });

    const table = await screen.findByRole("table", { name: "Fontes do workspace" });
    const [, row] = within(table).getAllByRole("row");
    if (row === undefined) {
      throw new Error("No source row");
    }
    expect(within(row).getByRole("link", { name: "erp-local" })).toBeInTheDocument();
    expect(within(row).getByText("Runner local")).toBeInTheDocument();
    expect(within(row).getByText("erp-core")).toBeInTheDocument();
  });
});
