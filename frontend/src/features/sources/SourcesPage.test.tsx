import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Role } from "@/lib/api/auth";
import { RUN_POLL_INTERVAL_MS } from "@/lib/api/sources";
import {
  COLLECTION_ID,
  FOLDER_SOURCE_ID,
  makeFolderSource,
  makeMe,
  makeRun,
  makeSource,
  makeWorkspace,
  OTHER_COLLECTION_ID,
  OTHER_WORKSPACE_ID,
  SOURCE_ID,
  WORKSPACE_ID,
} from "@/test/factories";
import {
  collectionsAs,
  meAs,
  sourceActionFails,
  sourcesAs,
  sourcesServerError,
  sourceStore,
} from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

import { SourcesPage } from "./SourcesPage";

const PATH = `/w/${WORKSPACE_ID}/sources`;
const TABLE = "Fontes do workspace";

type User = ReturnType<typeof userEvent.setup>;

function asRole(role: Role) {
  server.use(meAs(makeMe({ workspaces: [makeWorkspace({ role })] })));
}

async function renderSources() {
  const result = renderWithProviders({ path: PATH });
  await screen.findByRole("table", { name: TABLE });
  return result;
}

function rowOf(name: string): HTMLElement {
  const row = within(screen.getByRole("table", { name: TABLE }))
    .getAllByRole("row")
    .find((item) => item.textContent.includes(name));
  if (row === undefined) {
    throw new Error(`No row for ${name}`);
  }
  return row;
}

async function openCreate(user: User) {
  await user.click(screen.getByRole("button", { name: "Nova fonte" }));
  return screen.findByRole("dialog", { name: "Nova fonte" });
}

async function save(user: User, dialog: HTMLElement) {
  await user.click(within(dialog).getByRole("button", { name: "Salvar" }));
}

afterEach(() => {
  vi.useRealTimers();
});

describe("SourcesPage list", () => {
  it("test_sources_page_lists_sources_with_last_and_next_run", async () => {
    server.use(sourcesAs([makeSource(), makeFolderSource()]));
    await renderSources();

    expect(screen.getByRole("heading", { level: 1, name: "Fontes" })).toBeInTheDocument();
    const erp = rowOf("erp-core");
    expect(within(erp).getByRole("link", { name: "erp-core" })).toHaveAttribute(
      "href",
      `${PATH}/${SOURCE_ID}`,
    );
    expect(within(erp).getByText("Repositório Git")).toBeInTheDocument();
    expect(within(erp).getByText("Código ERP")).toBeInTheDocument();
    expect(within(erp).getByText("Concluída")).toBeInTheDocument();
    expect(within(erp).getByText("há 7 dias")).toBeInTheDocument();
    expect(within(erp).getByText("Sem agendamento")).toBeInTheDocument();
    const manuais = rowOf("manuais");
    expect(within(manuais).getByText("/sources/manuais")).toBeInTheDocument();
    expect(within(manuais).getByText("Pasta")).toBeInTheDocument();
    expect(within(manuais).getByText("Manuais")).toBeInTheDocument();
    expect(within(manuais).getByText("Nunca sincronizada")).toBeInTheDocument();
    expect(within(manuais).getByText("em 15 horas")).toBeInTheDocument();
    expect(within(manuais).getByText("Todos os dias às 03:00 (UTC)")).toBeInTheDocument();
  });

  it("test_sources_page_flags_inactive_source_and_paused_schedule", async () => {
    server.use(
      sourcesAs([
        makeSource({ active: false, schedule_cron: "0 3 * * *", schedule_enabled: false }),
      ]),
    );
    await renderSources();

    const erp = rowOf("erp-core");
    expect(within(erp).getByText("Desativada")).toBeInTheDocument();
    expect(within(erp).getByText("Agendamento pausado")).toBeInTheDocument();
    expect(within(erp).getByRole("button", { name: "Sincronizar erp-core agora" })).toBeDisabled();
  });

  it("test_sources_page_viewer_reads_without_actions", async () => {
    asRole("viewer");
    await renderSources();

    expect(rowOf("erp-core")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Nova fonte" })).not.toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Ações" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Sincronizar/ })).not.toBeInTheDocument();
  });

  it("test_sources_page_without_collections_points_to_collections", async () => {
    server.use(...collectionsAs([]), sourcesAs([]));
    await renderSources();

    expect(screen.queryByRole("button", { name: "Nova fonte" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ir para coleções" })).toHaveAttribute(
      "href",
      `/w/${WORKSPACE_ID}/collections`,
    );
    expect(screen.getByText("Nenhuma fonte cadastrada.")).toBeInTheDocument();
  });

  it("test_sources_page_retries_after_load_failure", async () => {
    const user = userEvent.setup();
    server.use(sourcesServerError);
    renderWithProviders({ path: PATH });

    expect(await screen.findByText("Não foi possível carregar as fontes.")).toHaveRole("alert");
    server.use(sourcesAs());
    await user.click(screen.getByRole("button", { name: "Tentar novamente" }));

    expect(await screen.findByRole("table", { name: TABLE })).toBeInTheDocument();
  });

  it("test_sources_page_renders_title_outside_a_membership", async () => {
    renderWithProviders({
      path: `/w/${OTHER_WORKSPACE_ID}/sources`,
      routes: [{ path: "/w/:workspaceId/sources", element: <SourcesPage /> }],
    });

    expect(await screen.findByRole("heading", { level: 1, name: "Fontes" })).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});

describe("SourcesPage create", () => {
  it("test_create_git_source_validates_and_saves", async () => {
    const user = userEvent.setup();
    const store = sourceStore([]);
    server.use(...store.handlers);
    await renderSources();

    const dialog = await openCreate(user);
    expect(within(dialog).getByRole("combobox", { name: "Coleção" })).toHaveTextContent(
      "Código ERP",
    );
    expect(within(dialog).getByRole("radio", { name: "Repositório Git" })).toBeChecked();
    expect(within(dialog).getByText(/No Docker Compose essa pasta é \/sources/)).toBeVisible();
    await user.type(within(dialog).getByLabelText("Caminho do clone"), "repos/erp");
    await user.clear(within(dialog).getByLabelText(/Commits indexados/));
    await user.type(within(dialog).getByLabelText(/Commits indexados/), "9000");
    await save(user, dialog);

    expect(await within(dialog).findByText("Informe o nome da fonte.")).toBeInTheDocument();
    expect(
      within(dialog).getByText("Use um caminho absoluto, como /sources/erp-core."),
    ).toBeInTheDocument();
    expect(within(dialog).getByText("Informe um número inteiro de 0 a 5000.")).toBeInTheDocument();
    expect(store.created).toEqual([]);

    await user.type(within(dialog).getByLabelText("Nome"), "erp-core");
    await user.clear(within(dialog).getByLabelText("Caminho do clone"));
    await user.type(within(dialog).getByLabelText("Caminho do clone"), "/sources/erp-core");
    await user.type(within(dialog).getByLabelText("Branch (opcional)"), "main");
    await user.clear(within(dialog).getByLabelText(/Commits indexados/));
    await user.type(within(dialog).getByLabelText(/Commits indexados/), "50");
    await save(user, dialog);

    expect(
      await screen.findByText('Fonte erp-core criada. Use "Sincronizar agora" para indexá-la.'),
    ).toHaveRole("status");
    expect(store.created).toEqual([
      {
        collection_id: COLLECTION_ID,
        kind: "git",
        name: "erp-core",
        config: { path: "/sources/erp-core", branch: "main", initial_commit_limit: 50 },
        include_globs: [],
        exclude_globs: [],
        schedule_cron: null,
        schedule_enabled: false,
        active: true,
      },
    ]);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(rowOf("erp-core")).toBeInTheDocument();
  });

  it("test_create_git_source_by_url_requires_public_https", async () => {
    const user = userEvent.setup();
    const store = sourceStore([]);
    server.use(...store.handlers);
    await renderSources();

    const dialog = await openCreate(user);
    await user.type(within(dialog).getByLabelText("Nome"), "erp-remoto");
    await user.click(within(dialog).getByRole("radio", { name: "URL pública (https)" }));
    expect(within(dialog).queryByLabelText("Caminho do clone")).not.toBeInTheDocument();
    await user.type(within(dialog).getByLabelText("URL do repositório"), "http://x.test/erp.git");
    await save(user, dialog);

    expect(
      await within(dialog).findByText("Informe uma URL https pública, sem usuário ou senha."),
    ).toBeInTheDocument();
    await user.clear(within(dialog).getByLabelText("URL do repositório"));
    await user.type(within(dialog).getByLabelText("URL do repositório"), "https://x.test/erp.git");
    await save(user, dialog);

    await screen.findByText(/Fonte erp-remoto criada/);
    expect(store.created[0]?.config).toEqual({
      url: "https://x.test/erp.git",
      initial_commit_limit: 200,
    });
  });

  it("test_create_folder_source_with_globs_and_preset_schedule", async () => {
    const user = userEvent.setup();
    const store = sourceStore([]);
    server.use(...store.handlers);
    await renderSources();

    const dialog = await openCreate(user);
    await user.type(within(dialog).getByLabelText("Nome"), "manuais");
    await user.click(within(dialog).getByRole("combobox", { name: "Coleção" }));
    await user.click(await screen.findByRole("option", { name: "Manuais" }));
    await user.click(within(dialog).getByRole("radio", { name: "Pasta" }));
    expect(within(dialog).queryByLabelText("Branch (opcional)")).not.toBeInTheDocument();
    await user.type(within(dialog).getByLabelText("Caminho da pasta"), "/sources/manuais");
    await user.type(within(dialog).getByLabelText(/^Incluir/), "**/*.md{enter}**/*.txt");
    await user.type(within(dialog).getByLabelText(/^Excluir/), "rascunhos/**");
    await user.click(within(dialog).getByRole("checkbox", { name: "Sincronizar automaticamente" }));
    const presets = within(dialog).getByRole("group", { name: "Agendamentos prontos" });
    await user.click(within(presets).getByRole("button", { name: "Dias úteis às 6h (UTC)" }));

    expect(within(dialog).getByLabelText("Agendamento (cron, UTC)")).toHaveValue("0 6 * * 1-5");
    expect(within(dialog).getByText("De segunda a sexta às 06:00 (UTC)")).toBeInTheDocument();
    await save(user, dialog);

    await screen.findByText(/Fonte manuais criada/);
    expect(store.created).toEqual([
      {
        collection_id: OTHER_COLLECTION_ID,
        kind: "folder",
        name: "manuais",
        config: { path: "/sources/manuais" },
        include_globs: ["**/*.md", "**/*.txt"],
        exclude_globs: ["rascunhos/**"],
        schedule_cron: "0 6 * * 1-5",
        schedule_enabled: true,
        active: true,
      },
    ]);
  });

  it("test_create_source_rejects_invalid_cron_and_reads_custom_ones", async () => {
    const user = userEvent.setup();
    const store = sourceStore([]);
    server.use(...store.handlers);
    await renderSources();

    const dialog = await openCreate(user);
    await user.type(within(dialog).getByLabelText("Nome"), "erp-core");
    await user.type(within(dialog).getByLabelText("Caminho do clone"), "/sources/erp-core");
    await user.click(within(dialog).getByRole("checkbox", { name: "Sincronizar automaticamente" }));
    await save(user, dialog);

    expect(
      await within(dialog).findByText(
        "Informe o agendamento ou desmarque a sincronização automática.",
      ),
    ).toBeInTheDocument();
    const cron = within(dialog).getByLabelText("Agendamento (cron, UTC)");
    await user.type(cron, "todo dia");
    await save(user, dialog);
    expect(
      await within(dialog).findByText("Use uma expressão cron de cinco campos, como 0 3 * * *."),
    ).toBeInTheDocument();

    await user.clear(cron);
    await user.type(cron, "0 3 1 1 *");
    expect(
      within(dialog).getByText("Expressão personalizada: o servidor confere ao salvar."),
    ).toBeInTheDocument();
    expect(store.created).toEqual([]);
  });

  it("test_create_source_shows_server_validation_error", async () => {
    const user = userEvent.setup();
    server.use(sourceActionFails("create", 422, "source_schedule_invalid"));
    await renderSources();

    const dialog = await openCreate(user);
    await user.type(within(dialog).getByLabelText("Nome"), "erp-core");
    await user.type(within(dialog).getByLabelText("Caminho do clone"), "/sources/erp-core");
    await save(user, dialog);

    expect(
      await within(dialog).findByText("O agendamento deve ser uma expressão cron de cinco campos."),
    ).toHaveRole("alert");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});

describe("SourcesPage edit and delete", () => {
  it("test_edit_source_keeps_kind_and_collection_and_clears_cron", async () => {
    const user = userEvent.setup();
    const store = sourceStore([makeFolderSource()]);
    server.use(...store.handlers);
    await renderSources();

    await user.click(screen.getByRole("button", { name: "Editar manuais" }));
    const dialog = await screen.findByRole("dialog", { name: "Editar fonte" });
    expect(within(dialog).getByRole("combobox", { name: "Coleção" })).toBeDisabled();
    expect(within(dialog).getByRole("radio", { name: "Pasta" })).toBeDisabled();
    expect(within(dialog).getByLabelText("Caminho da pasta")).toHaveValue("/sources/manuais");
    expect(within(dialog).getByText("Todos os dias às 03:00 (UTC)")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("checkbox", { name: "Sincronizar automaticamente" }));
    await user.clear(within(dialog).getByLabelText("Agendamento (cron, UTC)"));
    await user.click(within(dialog).getByRole("checkbox", { name: "Ativa" }));
    await save(user, dialog);

    expect(await screen.findByText("Fonte manuais atualizada.")).toHaveRole("status");
    expect(store.changes).toEqual([
      {
        sourceId: FOLDER_SOURCE_ID,
        body: {
          name: "manuais",
          config: { path: "/sources/manuais" },
          include_globs: ["**/*.md"],
          exclude_globs: ["rascunhos/**"],
          schedule_cron: null,
          schedule_enabled: false,
          active: false,
        },
      },
    ]);
    expect(within(rowOf("manuais")).getByText("Desativada")).toBeInTheDocument();
  });

  it("test_delete_source_after_confirmation", async () => {
    const user = userEvent.setup();
    const store = sourceStore([makeSource(), makeFolderSource()]);
    server.use(...store.handlers);
    await renderSources();

    await user.click(screen.getByRole("button", { name: "Excluir erp-core" }));
    const confirm = await screen.findByRole("alertdialog", { name: "Excluir a fonte erp-core?" });
    await user.click(within(confirm).getByRole("button", { name: "Excluir" }));

    expect(await screen.findByText("A fonte erp-core foi excluída.")).toHaveRole("status");
    expect(store.deleted).toEqual([SOURCE_ID]);
    await waitFor(() => {
      expect(screen.queryByRole("link", { name: "erp-core" })).not.toBeInTheDocument();
    });
  });

  it("test_delete_source_failure_shows_alert", async () => {
    const user = userEvent.setup();
    server.use(sourceActionFails("delete", 404, "source_not_found"));
    await renderSources();

    await user.click(screen.getByRole("button", { name: "Excluir erp-core" }));
    await user.click(await screen.findByRole("button", { name: "Excluir" }));

    expect(await screen.findByText("A fonte não existe ou foi excluída.")).toHaveRole("alert");
  });
});

describe("SourcesPage sync", () => {
  it("test_sync_now_queues_a_run_and_offers_cancel", async () => {
    const user = userEvent.setup();
    const store = sourceStore();
    server.use(...store.handlers);
    await renderSources();

    await user.click(screen.getByRole("button", { name: "Sincronizar erp-core agora" }));

    expect(await screen.findByText("Sincronização de erp-core na fila.")).toHaveRole("status");
    expect(store.synced).toEqual([SOURCE_ID]);
    expect(await within(rowOf("erp-core")).findByText("Na fila")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Cancelar a sincronização de erp-core" }),
    ).toBeEnabled();
  });

  it("test_cancel_sync_of_a_running_source", async () => {
    const user = userEvent.setup();
    const running = makeRun({ status: "running", finished_at: null });
    const store = sourceStore([makeSource({ last_run: running })], {
      runs: { [SOURCE_ID]: [running] },
    });
    server.use(...store.handlers);
    await renderSources();

    expect(within(rowOf("erp-core")).getByText("Em execução")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Cancelar a sincronização de erp-core" }));

    expect(await screen.findByText("Cancelamento da sincronização de erp-core pedido.")).toHaveRole(
      "status",
    );
    expect(store.cancelled).toEqual([SOURCE_ID]);
    expect(await within(rowOf("erp-core")).findByText("Cancelada")).toBeInTheDocument();
  });

  it("test_sync_failure_shows_reason", async () => {
    const user = userEvent.setup();
    server.use(sourceActionFails("sync", 503, "sync_unavailable"));
    await renderSources();

    await user.click(screen.getByRole("button", { name: "Sincronizar erp-core agora" }));

    expect(
      await screen.findByText(
        "O serviço de sincronização está indisponível. Tente de novo em instantes.",
      ),
    ).toHaveRole("alert");
  });

  it("test_cancel_failure_shows_reason", async () => {
    const user = userEvent.setup();
    server.use(
      sourcesAs([makeSource({ last_run: makeRun({ status: "queued" }) })]),
      sourceActionFails("cancel", 409, "sync_not_running"),
    );
    await renderSources();

    await user.click(screen.getByRole("button", { name: "Cancelar a sincronização de erp-core" }));

    expect(await screen.findByText("Não há sincronização em andamento nesta fonte.")).toHaveRole(
      "alert",
    );
  });

  it("test_sources_page_polls_while_a_run_is_active", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const running = makeRun({ status: "running", finished_at: null });
    const store = sourceStore([makeSource({ last_run: running })]);
    server.use(...store.handlers);
    await renderSources();
    expect(within(rowOf("erp-core")).getByText("Em execução")).toBeInTheDocument();

    store.finishRun(SOURCE_ID, "succeeded");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(RUN_POLL_INTERVAL_MS);
    });

    expect(await within(rowOf("erp-core")).findByText("Concluída")).toBeInTheDocument();
  });
});
