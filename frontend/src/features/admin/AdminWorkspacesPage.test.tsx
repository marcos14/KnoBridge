import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it } from "vitest";

import {
  adminId,
  makeAdminWorkspace,
  makeAdminWorkspaces,
  makeMe,
  OTHER_WORKSPACE_ID,
  WORKSPACE_ID,
} from "@/test/factories";
import {
  adminWorkspacesAs,
  adminWorkspacesServerError,
  adminWorkspaceStore,
  createWorkspaceFails,
  meAs,
  updateWorkspaceFails,
} from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

const TABLE = "Workspaces";

type User = ReturnType<typeof userEvent.setup>;

function setup(initial = makeAdminWorkspaces()) {
  server.use(meAs(makeMe({ is_superadmin: true })));
  const store = adminWorkspaceStore(initial);
  server.use(...store.handlers);
  return store;
}

function countMeRequests() {
  const calls: string[] = [];
  server.use(
    http.get("*/v1/me", ({ request }) => {
      calls.push(request.url);
      return undefined;
    }),
  );
  return calls;
}

async function renderPage() {
  const result = renderWithProviders({ path: "/admin/workspaces" });
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

async function fillCreate(user: User, values: { name?: string; slug?: string; email?: string }) {
  await user.click(screen.getByRole("button", { name: "Criar workspace" }));
  const dialog = await screen.findByRole("dialog", { name: "Criar workspace" });
  if (values.name !== undefined) {
    await user.type(within(dialog).getByLabelText("Nome"), values.name);
  }
  if (values.slug !== undefined) {
    await user.type(within(dialog).getByLabelText("Identificador (opcional)"), values.slug);
  }
  if (values.email !== undefined) {
    await user.type(within(dialog).getByLabelText("E-mail do proprietário"), values.email);
  }
  await user.click(within(dialog).getByRole("button", { name: "Criar" }));
  return dialog;
}

describe("AdminWorkspacesPage list", () => {
  it("test_admin_workspaces_lists_every_workspace", async () => {
    setup();
    await renderPage();

    expect(
      screen.getByRole("heading", { level: 1, name: "Workspaces da instância" }),
    ).toBeInTheDocument();
    expect(within(rowOf("Acme Suporte")).getByText("acme-suporte")).toBeInTheDocument();
    expect(within(rowOf("Acme Suporte")).getByText("Ativo")).toBeInTheDocument();
    expect(within(rowOf("Acme Suporte")).getByText("4")).toBeInTheDocument();
    expect(within(rowOf("Beta Help")).getByText("Suspenso")).toBeInTheDocument();
    expect(
      within(rowOf("Beta Help")).getByRole("button", { name: "Reativar Beta Help" }),
    ).toBeInTheDocument();
  });

  it("test_admin_workspaces_search_queries_the_api", async () => {
    const store = setup();
    const user = userEvent.setup();
    await renderPage();

    await user.type(screen.getByRole("searchbox", { name: "Buscar" }), " beta {Enter}");

    await waitFor(() => {
      expect(store.queries.at(-1)?.get("q")).toBe("beta");
    });
    const table = screen.getByRole("table", { name: TABLE });
    await waitFor(() => {
      expect(within(table).queryByText("Acme Suporte")).not.toBeInTheDocument();
    });
    expect(within(table).getByText("Beta Help")).toBeInTheDocument();
    expect(store.queries.at(-1)?.get("offset")).toBe("0");
  });

  it("test_admin_workspaces_search_without_results_shows_empty", async () => {
    setup();
    const user = userEvent.setup();
    await renderPage();

    await user.type(screen.getByRole("searchbox", { name: "Buscar" }), "zzz");
    await user.click(screen.getByRole("button", { name: "Buscar" }));

    expect(await screen.findByText("Nenhum workspace encontrado.")).toBeInTheDocument();
  });

  it("test_admin_workspaces_pages_on_the_server", async () => {
    const many = Array.from({ length: 23 }, (_, index) =>
      makeAdminWorkspace({ id: adminId(50 + index), name: `WS ${String(index).padStart(2, "0")}` }),
    );
    const store = setup(many);
    const user = userEvent.setup();
    await renderPage();

    await user.click(screen.getByRole("button", { name: "Próxima" }));

    expect(await screen.findByText("21–23 de 23")).toBeInTheDocument();
    expect(store.queries.at(-1)?.get("offset")).toBe("20");
  });

  it("test_admin_workspaces_load_error_offers_retry", async () => {
    server.use(meAs(makeMe({ is_superadmin: true })), adminWorkspacesServerError);
    const user = userEvent.setup();
    renderWithProviders({ path: "/admin/workspaces" });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não foi possível carregar a lista.",
    );
    server.use(adminWorkspacesAs());
    await user.click(screen.getByRole("button", { name: "Tentar novamente" }));

    expect(await screen.findByRole("table", { name: TABLE })).toBeInTheDocument();
  });
});

describe("AdminWorkspacesPage create", () => {
  it("test_admin_workspaces_create_sends_owner_email_and_generated_slug", async () => {
    const store = setup();
    const user = userEvent.setup();
    await renderPage();

    await fillCreate(user, { name: "Gama Suporte", email: "owner@example.test" });

    expect(
      await screen.findByText(
        "Workspace Gama Suporte criado. Enviamos o convite de proprietário para owner@example.test.",
      ),
    ).toBeInTheDocument();
    expect(store.created).toEqual([
      { name: "Gama Suporte", slug: null, owner_email: "owner@example.test" },
    ]);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(await screen.findByText("gama-suporte")).toBeInTheDocument();
  });

  it("test_admin_workspaces_create_sends_chosen_slug", async () => {
    const store = setup();
    const user = userEvent.setup();
    await renderPage();

    await fillCreate(user, { name: "Gama", slug: "gama-2", email: "owner@example.test" });

    await waitFor(() => {
      expect(store.created).toEqual([
        { name: "Gama", slug: "gama-2", owner_email: "owner@example.test" },
      ]);
    });
  });

  it("test_admin_workspaces_create_shows_slug_taken", async () => {
    const store = setup();
    const user = userEvent.setup();
    await renderPage();

    const dialog = await fillCreate(user, {
      name: "Acme",
      slug: "acme-suporte",
      email: "owner@example.test",
    });

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "Este identificador já está em uso.",
    );
    expect(store.created).toEqual([]);
  });

  it("test_admin_workspaces_create_validates_fields", async () => {
    const store = setup();
    const user = userEvent.setup();
    await renderPage();

    const dialog = await fillCreate(user, { slug: "Acme X" });

    expect(await within(dialog).findByText("Informe o nome do workspace.")).toBeInTheDocument();
    expect(
      within(dialog).getByText(
        "Use só letras minúsculas, números e hífens, sem hífen no início nem no fim.",
      ),
    ).toBeInTheDocument();
    expect(within(dialog).getByText("Informe seu e-mail.")).toBeInTheDocument();
    expect(store.created).toEqual([]);
  });

  it("test_admin_workspaces_create_reopens_clean", async () => {
    setup();
    server.use(createWorkspaceFails(500, "internal_error"));
    const user = userEvent.setup();
    await renderPage();
    const dialog = await fillCreate(user, { name: "Gama", email: "owner@example.test" });
    expect(await within(dialog).findByRole("alert")).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: "Cancelar" }));
    await user.click(screen.getByRole("button", { name: "Criar workspace" }));

    const reopened = await screen.findByRole("dialog", { name: "Criar workspace" });
    expect(within(reopened).queryByRole("alert")).not.toBeInTheDocument();
    expect(within(reopened).getByLabelText("Nome")).toHaveValue("");
  });
});

describe("AdminWorkspacesPage rename and status", () => {
  it("test_admin_workspaces_rename_sends_new_name", async () => {
    const store = setup();
    const user = userEvent.setup();
    await renderPage();

    await user.click(screen.getByRole("button", { name: "Renomear Beta Help" }));
    const dialog = await screen.findByRole("dialog", { name: "Renomear Beta Help" });
    const input = within(dialog).getByLabelText("Novo nome");
    expect(input).toHaveValue("Beta Help");
    await user.clear(input);
    await user.type(input, "Beta Atendimento");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(
      await screen.findByText("Workspace renomeado para Beta Atendimento."),
    ).toBeInTheDocument();
    expect(store.changes).toEqual([
      { workspaceId: OTHER_WORKSPACE_ID, change: { name: "Beta Atendimento" } },
    ]);
  });

  it("test_admin_workspaces_rename_requires_a_name", async () => {
    const store = setup();
    const user = userEvent.setup();
    await renderPage();

    await user.click(screen.getByRole("button", { name: "Renomear Beta Help" }));
    const dialog = await screen.findByRole("dialog", { name: "Renomear Beta Help" });
    await user.clear(within(dialog).getByLabelText("Novo nome"));
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await within(dialog).findByText("Informe o nome do workspace.")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Cancelar" }));
    expect(store.changes).toEqual([]);
  });

  it("test_admin_workspaces_suspend_asks_confirmation_and_refreshes_me", async () => {
    const store = setup();
    const user = userEvent.setup();
    await renderPage();
    const meCalls = countMeRequests();

    await user.click(screen.getByRole("button", { name: "Suspender Acme Suporte" }));
    const confirm = await screen.findByRole("alertdialog", { name: "Suspender Acme Suporte?" });
    await user.click(within(confirm).getByRole("button", { name: "Suspender" }));

    expect(await screen.findByText("Workspace Acme Suporte suspenso.")).toBeInTheDocument();
    expect(store.changes).toEqual([{ workspaceId: WORKSPACE_ID, change: { status: "suspended" } }]);
    await waitFor(() => {
      expect(meCalls.length).toBeGreaterThan(0);
    });
    expect(
      await within(rowOf("Acme Suporte")).findByRole("button", {
        name: "Reativar Acme Suporte",
      }),
    ).toBeInTheDocument();
  });

  it("test_admin_workspaces_suspend_cancel_changes_nothing", async () => {
    const store = setup();
    const user = userEvent.setup();
    await renderPage();

    await user.click(screen.getByRole("button", { name: "Suspender Acme Suporte" }));
    const confirm = await screen.findByRole("alertdialog");
    await user.click(within(confirm).getByRole("button", { name: "Cancelar" }));

    expect(store.changes).toEqual([]);
  });

  it("test_admin_workspaces_reactivate_without_membership_keeps_me", async () => {
    const store = setup();
    const user = userEvent.setup();
    await renderPage();
    const meCalls = countMeRequests();

    await user.click(screen.getByRole("button", { name: "Reativar Beta Help" }));
    const confirm = await screen.findByRole("alertdialog", { name: "Reativar Beta Help?" });
    await user.click(within(confirm).getByRole("button", { name: "Reativar" }));

    expect(await screen.findByText("Workspace Beta Help reativado.")).toBeInTheDocument();
    expect(store.changes).toEqual([
      { workspaceId: OTHER_WORKSPACE_ID, change: { status: "active" } },
    ]);
    expect(meCalls).toEqual([]);
  });

  it("test_admin_workspaces_update_error_is_shown", async () => {
    setup();
    server.use(updateWorkspaceFails(404, "not_found"));
    const user = userEvent.setup();
    await renderPage();

    await user.click(screen.getByRole("button", { name: "Reativar Beta Help" }));
    await user.click(
      within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Reativar" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("O item procurado não existe.");
  });
});
