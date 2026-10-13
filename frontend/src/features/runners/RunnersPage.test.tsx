import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { Role } from "@/lib/api/auth";
import {
  makeMe,
  makeNewRunner,
  makeRunner,
  makeWorkspace,
  OTHER_RUNNER_ID,
  OTHER_WORKSPACE_ID,
  REVOKED_RUNNER_ID,
  RUNNER_ID,
  RUNNER_TOKEN,
  WORKSPACE_ID,
} from "@/test/factories";
import {
  meAs,
  pendingPost,
  runnerActionFails,
  runnersAs,
  runnersRecorder,
  runnersServerError,
  runnerStore,
} from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

import { RunnersPage } from "./RunnersPage";

const PATH = `/w/${WORKSPACE_ID}/runners`;
const TABLE = "Runners do workspace";

type User = ReturnType<typeof userEvent.setup>;

function asRole(role: Role) {
  server.use(meAs(makeMe({ workspaces: [makeWorkspace({ role })] })));
}

async function renderRunners() {
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
  await user.click(screen.getByRole("button", { name: "Novo runner" }));
  return screen.findByRole("dialog", { name: "Novo runner" });
}

async function confirm(user: User, button: string, confirmLabel: string) {
  await user.click(screen.getByRole("button", { name: button }));
  const dialog = await screen.findByRole("alertdialog");
  await user.click(within(dialog).getByRole("button", { name: confirmLabel }));
}

describe("RunnersPage list", () => {
  it("test_runners_page_lists_presence_version_executors_and_repositories", async () => {
    await renderRunners();

    expect(screen.getByRole("heading", { level: 1, name: "Runners" })).toBeInTheDocument();
    const ana = rowOf("notebook-ana");
    expect(within(ana).getByText("Token kbr_ab12cd34_…")).toBeInTheDocument();
    expect(within(ana).getByText("Online")).toBeInTheDocument();
    expect(within(ana).getByText("há 30 segundos")).toBeInTheDocument();
    expect(within(ana).getByText("0.1.0")).toBeInTheDocument();
    expect(within(ana).getByText("Claude Code 2.0.1")).toBeInTheDocument();
    expect(within(ana).getByText(/Codex/)).toHaveTextContent("Codex (indisponível)");
    expect(within(ana).getByText(/erp-core/)).toHaveTextContent("erp-core · main");
    expect(within(ana).getByText(/portal/)).toHaveTextContent(
      "portal · develop · alterações locais",
    );
    expect(within(ana).getByRole("button", { name: "Revogar notebook-ana" })).toBeInTheDocument();

    const build = rowOf("servidor-build");
    expect(within(build).getByText("Offline")).toBeInTheDocument();
    expect(within(build).getByText("Nunca conectou")).toBeInTheDocument();
    expect(within(build).getByText("—")).toBeInTheDocument();
    expect(within(build).getAllByText("Nenhum informado")).toHaveLength(2);

    const old = rowOf("antigo");
    expect(within(old).getByText("Revogado")).toBeInTheDocument();
    expect(within(old).queryByRole("button", { name: /Revogar/ })).not.toBeInTheDocument();
    expect(within(old).getByRole("button", { name: "Excluir antigo" })).toBeInTheDocument();
  });

  it("test_runners_page_status_follows_last_seen_at", async () => {
    server.use(
      runnersAs([
        // The API said online when it answered, but the last contact is 5 minutes old.
        makeRunner({ online: true, last_seen_at: "2026-10-10T11:55:00Z" }),
      ]),
    );
    await renderRunners();

    const ana = rowOf("notebook-ana");
    expect(within(ana).getByText("Offline")).toBeInTheDocument();
    expect(within(ana).getByText("há 5 minutos")).toBeInTheDocument();
  });

  it("test_runners_page_shows_unknown_executor_and_missing_version_as_reported", async () => {
    server.use(
      runnersAs([
        makeRunner({
          capabilities: {
            platform: "linux",
            executors: [
              { name: "claude_code", available: true, version: null, authenticated: false },
              { name: "gemini", available: true, version: "1.0", authenticated: null },
            ],
            repositories: [{ name: "solto", head_commit: null, branch: null, dirty: false }],
          },
        }),
      ]),
    );
    await renderRunners();

    const ana = rowOf("notebook-ana");
    expect(within(ana).getByText(/Claude Code/)).toHaveTextContent("Claude Code (sem login)");
    expect(within(ana).getByText("gemini 1.0")).toBeInTheDocument();
    expect(within(ana).getByText("solto")).toBeInTheDocument();
  });

  it("test_runners_page_shows_empty_list", async () => {
    server.use(runnersAs([]));
    await renderRunners();

    expect(screen.getByText(/Nenhum runner cadastrado\. Use "Novo runner"/)).toBeInTheDocument();
  });

  it("test_runners_page_retries_after_load_failure", async () => {
    const user = userEvent.setup();
    server.use(runnersServerError);
    renderWithProviders({ path: PATH });

    expect(await screen.findByText("Carregando runners…")).toHaveRole("status");
    expect(await screen.findByText("Não foi possível carregar os runners.")).toHaveRole("alert");
    server.use(runnersAs());
    await user.click(screen.getByRole("button", { name: "Tentar novamente" }));

    expect(await screen.findByRole("table", { name: TABLE })).toBeInTheDocument();
  });

  it("test_runners_page_renders_title_outside_a_membership", async () => {
    renderWithProviders({
      path: `/w/${OTHER_WORKSPACE_ID}/runners`,
      routes: [{ path: "/w/:workspaceId/runners", element: <RunnersPage /> }],
    });

    expect(await screen.findByRole("heading", { level: 1, name: "Runners" })).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});

describe("RunnersPage search, filter and sort", () => {
  it("test_runners_page_searches_filters_and_sorts_on_the_api", async () => {
    const user = userEvent.setup();
    const recorder = runnersRecorder();
    server.use(recorder.handler);
    const { router } = await renderRunners();

    await user.type(screen.getByRole("searchbox", { name: "Buscar runners" }), "servidor");
    await waitFor(() => {
      expect(recorder.last()).toBe("query=servidor&sort=name");
    });
    await waitFor(() => {
      expect(screen.queryByText("notebook-ana")).not.toBeInTheDocument();
    });
    expect(rowOf("servidor-build")).toBeInTheDocument();

    await user.click(screen.getByRole("combobox", { name: "Status" }));
    await user.click(await screen.findByRole("option", { name: "Offline" }));
    await waitFor(() => {
      expect(recorder.last()).toBe("query=servidor&sort=name&status=offline");
    });

    await user.click(screen.getByRole("combobox", { name: "Ordenar por" }));
    await user.click(await screen.findByRole("option", { name: "Contato mais recente" }));
    await waitFor(() => {
      expect(router.state.location.search).toBe("?q=servidor&status=offline&sort=-last_seen_at");
    });
  });

  it("test_runners_page_filtered_empty_state_offers_clear", async () => {
    const user = userEvent.setup();
    server.use(runnersRecorder([]).handler);
    const { router } = renderWithProviders({ path: `${PATH}?status=revoked` });

    expect(
      await screen.findByText("Nada encontrado com a busca e os filtros atuais."),
    ).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Limpar filtros" }));

    await waitFor(() => {
      expect(router.state.location.search).toBe("");
    });
  });
});

describe("RunnersPage roles", () => {
  it.each(["editor", "viewer"] as const)("test_runners_page_%s_gets_forbidden", async (role) => {
    asRole(role);
    renderWithProviders({ path: PATH });

    expect(
      await screen.findByRole("heading", { level: 1, name: "Acesso negado" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Runners" })).not.toBeInTheDocument();
  });

  it("test_runners_page_admin_sees_the_menu_item", async () => {
    asRole("admin");
    await renderRunners();

    expect(screen.getByRole("link", { name: "Runners" })).toHaveAttribute("href", PATH);
    expect(screen.getByRole("button", { name: "Novo runner" })).toBeEnabled();
  });
});

describe("RunnersPage create", () => {
  it("test_create_runner_shows_the_token_once_with_the_setup_commands", async () => {
    const user = userEvent.setup();
    const store = runnerStore([]);
    server.use(...store.handlers);
    await renderRunners();

    let dialog = await openCreate(user);
    await user.click(within(dialog).getByRole("button", { name: "Criar runner" }));
    expect(await within(dialog).findByText("Informe o nome do runner.")).toBeInTheDocument();
    expect(store.created).toEqual([]);

    await user.type(within(dialog).getByLabelText("Nome"), "  notebook-bia ");
    await user.click(within(dialog).getByRole("button", { name: "Criar runner" }));

    dialog = await screen.findByRole("dialog", { name: "Runner notebook-bia criado" });
    expect(store.created).toEqual(["notebook-bia"]);
    expect(within(dialog).getByText(RUNNER_TOKEN)).toBeInTheDocument();
    const commands = within(dialog).getByText(/knobridge-runner configure/);
    expect(commands).toHaveTextContent(
      `knobridge-runner configure --server-url ${window.location.origin} --repo nome=/caminho/do/checkout`,
    );
    expect(commands).not.toHaveTextContent("kbr_");

    const token = within(dialog).getByRole("region", { name: "Token do runner" });
    await user.click(within(token).getByRole("button", { name: "Copiar token" }));
    expect(await within(token).findByRole("status")).toHaveTextContent("Copiado.");
    await expect(navigator.clipboard.readText()).resolves.toBe(RUNNER_TOKEN);
    const setup = within(dialog).getByRole("region", { name: "Instalar e configurar" });
    await user.click(within(setup).getByRole("button", { name: "Copiar comandos" }));
    await expect(navigator.clipboard.readText()).resolves.toMatch(/^uv tool install \.\/runner\n/);

    await user.click(within(dialog).getByRole("button", { name: "Concluído" }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expect(screen.queryByText(RUNNER_TOKEN)).not.toBeInTheDocument();
    expect(rowOf("notebook-bia")).toBeInTheDocument();

    dialog = await openCreate(user);
    expect(within(dialog).getByLabelText("Nome")).toHaveValue("");
    expect(screen.queryByText(RUNNER_TOKEN)).not.toBeInTheDocument();
  });

  it("test_create_runner_reports_copy_failure", async () => {
    const user = userEvent.setup();
    vi.spyOn(navigator.clipboard, "writeText").mockRejectedValueOnce(new Error("blocked"));
    await renderRunners();

    const dialog = await openCreate(user);
    await user.type(within(dialog).getByLabelText("Nome"), "servidor-build-2");
    await user.click(within(dialog).getByRole("button", { name: "Criar runner" }));
    const created = await screen.findByRole("dialog", { name: /criado/ });
    await user.click(within(created).getByRole("button", { name: "Copiar token" }));

    expect(
      await within(created).findByText(
        "Não foi possível copiar. Selecione o texto e copie manualmente.",
      ),
    ).toHaveRole("status");
  });

  it("test_create_runner_with_taken_name_shows_the_error", async () => {
    const user = userEvent.setup();
    const store = runnerStore();
    server.use(...store.handlers);
    await renderRunners();

    const dialog = await openCreate(user);
    await user.type(within(dialog).getByLabelText("Nome"), "notebook-ana");
    await user.click(within(dialog).getByRole("button", { name: "Criar runner" }));

    expect(await within(dialog).findByText("Já existe um runner com esse nome.")).toBeVisible();
    expect(store.created).toEqual([]);
  });

  it("test_create_runner_disables_submit_while_saving", async () => {
    const user = userEvent.setup();
    server.use(pendingPost("*/v1/workspaces/:workspaceId/runners"));
    await renderRunners();

    const dialog = await openCreate(user);
    await user.type(within(dialog).getByLabelText("Nome"), "lento");
    await user.click(within(dialog).getByRole("button", { name: "Criar runner" }));

    expect(await within(dialog).findByRole("button", { name: "Enviando…" })).toBeDisabled();
  });

  it("test_create_runner_rejects_a_too_long_name", async () => {
    const user = userEvent.setup();
    await renderRunners();

    const dialog = await openCreate(user);
    await user.click(within(dialog).getByLabelText("Nome"));
    await user.paste("x".repeat(201));
    await user.click(within(dialog).getByRole("button", { name: "Criar runner" }));

    expect(await within(dialog).findByText("Use no máximo 200 caracteres.")).toBeInTheDocument();
  });
});

describe("RunnersPage revoke and delete", () => {
  it("test_revoke_runner_after_confirmation", async () => {
    const user = userEvent.setup();
    const store = runnerStore();
    server.use(...store.handlers);
    await renderRunners();

    await user.click(screen.getByRole("button", { name: "Revogar notebook-ana" }));
    const dialog = await screen.findByRole("alertdialog", {
      name: "Revogar o runner notebook-ana?",
    });
    await user.click(within(dialog).getByRole("button", { name: "Cancelar" }));
    expect(store.changes).toEqual([]);

    await confirm(user, "Revogar notebook-ana", "Revogar");

    expect(await screen.findByText("O runner notebook-ana foi revogado.")).toHaveRole("status");
    expect(store.changes).toEqual([{ runnerId: RUNNER_ID, body: { revoked: true } }]);
    await waitFor(() => {
      expect(within(rowOf("notebook-ana")).getByText("Revogado")).toBeInTheDocument();
    });
    expect(
      within(rowOf("notebook-ana")).queryByRole("button", { name: /Revogar/ }),
    ).not.toBeInTheDocument();
  });

  it("test_revoke_runner_failure_shows_the_error", async () => {
    const user = userEvent.setup();
    server.use(runnerActionFails("update", 404, "runner_not_found"));
    await renderRunners();

    await confirm(user, "Revogar notebook-ana", "Revogar");

    expect(await screen.findByText("Runner não encontrado.")).toBeInTheDocument();
  });

  it("test_delete_runner_after_confirmation", async () => {
    const user = userEvent.setup();
    const store = runnerStore();
    server.use(...store.handlers);
    await renderRunners();

    await confirm(user, "Excluir antigo", "Excluir");

    expect(await screen.findByText("O runner antigo foi excluído.")).toHaveRole("status");
    expect(store.deleted).toEqual([REVOKED_RUNNER_ID]);
    await waitFor(() => {
      expect(screen.queryByText("antigo")).not.toBeInTheDocument();
    });
  });

  it("test_delete_runner_in_use_is_refused", async () => {
    const user = userEvent.setup();
    const store = runnerStore([makeNewRunner()], { inUse: [OTHER_RUNNER_ID] });
    server.use(...store.handlers);
    await renderRunners();

    await confirm(user, "Excluir servidor-build", "Excluir");

    expect(
      await screen.findByText(
        "Este runner é usado por alguma fonte. Exclua a fonte ou troque o runner dela antes.",
      ),
    ).toBeInTheDocument();
    expect(store.deleted).toEqual([]);
    expect(rowOf("servidor-build")).toBeInTheDocument();
  });
});
