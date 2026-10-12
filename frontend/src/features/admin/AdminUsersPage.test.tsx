import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it } from "vitest";

import { makeAdminUsers, makeMe, memberId, USER_ID } from "@/test/factories";
import {
  adminUsersAs,
  adminUsersServerError,
  adminUserStore,
  meAs,
  updateUserFails,
} from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

const TABLE = "Usuários";

type User = ReturnType<typeof userEvent.setup>;

function setup(initial = makeAdminUsers()) {
  server.use(meAs(makeMe({ is_superadmin: true })));
  const store = adminUserStore(initial);
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
  const result = renderWithProviders({ path: "/admin/users" });
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

async function confirmAction(user: User, trigger: string, title: string, confirm: string) {
  await user.click(screen.getByRole("button", { name: trigger }));
  const dialog = await screen.findByRole("alertdialog", { name: title });
  await user.click(within(dialog).getByRole("button", { name: confirm }));
}

describe("AdminUsersPage list", () => {
  it("test_admin_users_lists_accounts_with_status_and_role", async () => {
    setup();
    await renderPage();

    expect(
      screen.getByRole("heading", { level: 1, name: "Usuários da instância" }),
    ).toBeInTheDocument();
    const ana = rowOf("Ana Teste");
    expect(within(ana).getByText("você")).toBeInTheDocument();
    expect(within(ana).getByText("Superadministrador")).toBeInTheDocument();
    expect(within(ana).queryByRole("button", { name: /^Suspender/ })).not.toBeInTheDocument();
    expect(
      within(ana).getByRole("button", { name: "Remover Ana Teste dos superadministradores" }),
    ).toBeInTheDocument();
    const carla = rowOf("Carla Souza");
    expect(within(carla).getByText("Suspenso")).toBeInTheDocument();
    expect(within(carla).getByText("e-mail não verificado")).toBeInTheDocument();
    expect(within(carla).getByRole("button", { name: "Reativar Carla Souza" })).toBeInTheDocument();
  });

  it("test_admin_users_search_queries_the_api", async () => {
    const store = setup();
    const user = userEvent.setup();
    await renderPage();

    await user.type(screen.getByRole("searchbox", { name: "Buscar" }), "carla@{Enter}");

    await waitFor(() => {
      expect(store.queries.at(-1)?.get("q")).toBe("carla@");
    });
    await waitFor(() => {
      expect(screen.queryByText("Bruno Lima")).not.toBeInTheDocument();
    });
  });

  it("test_admin_users_search_without_results_shows_empty", async () => {
    setup();
    const user = userEvent.setup();
    await renderPage();

    await user.type(screen.getByRole("searchbox", { name: "Buscar" }), "zzz{Enter}");

    expect(await screen.findByText("Nenhum usuário encontrado.")).toBeInTheDocument();
  });

  it("test_admin_users_load_error_offers_retry", async () => {
    server.use(meAs(makeMe({ is_superadmin: true })), adminUsersServerError);
    const user = userEvent.setup();
    renderWithProviders({ path: "/admin/users" });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não foi possível carregar a lista.",
    );
    server.use(adminUsersAs());
    await user.click(screen.getByRole("button", { name: "Tentar novamente" }));

    expect(await screen.findByRole("table", { name: TABLE })).toBeInTheDocument();
  });
});

describe("AdminUsersPage actions", () => {
  it("test_admin_users_suspend_with_confirmation", async () => {
    const store = setup();
    const user = userEvent.setup();
    await renderPage();
    const meCalls = countMeRequests();

    await confirmAction(user, "Suspender Bruno Lima", "Suspender Bruno Lima?", "Suspender");

    expect(await screen.findByText("Conta de Bruno Lima suspensa.")).toBeInTheDocument();
    expect(store.changes).toEqual([{ userId: memberId(1), change: { status: "suspended" } }]);
    expect(
      await within(rowOf("Bruno Lima")).findByRole("button", { name: "Reativar Bruno Lima" }),
    ).toBeInTheDocument();
    expect(meCalls).toEqual([]);
  });

  it("test_admin_users_suspend_cancel_changes_nothing", async () => {
    const store = setup();
    const user = userEvent.setup();
    await renderPage();

    await user.click(screen.getByRole("button", { name: "Suspender Bruno Lima" }));
    await user.click(
      within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Cancelar" }),
    );

    expect(store.changes).toEqual([]);
  });

  it("test_admin_users_reactivate", async () => {
    const store = setup();
    const user = userEvent.setup();
    await renderPage();

    await confirmAction(user, "Reativar Carla Souza", "Reativar Carla Souza?", "Reativar");

    expect(await screen.findByText("Conta de Carla Souza reativada.")).toBeInTheDocument();
    expect(store.changes).toEqual([{ userId: memberId(2), change: { status: "active" } }]);
  });

  it("test_admin_users_grant_superadmin", async () => {
    const store = setup();
    const user = userEvent.setup();
    await renderPage();

    await confirmAction(
      user,
      "Tornar Bruno Lima superadministrador",
      "Tornar Bruno Lima superadministrador?",
      "Tornar superadmin",
    );

    expect(await screen.findByText("Bruno Lima agora é superadministrador.")).toBeInTheDocument();
    expect(store.changes).toEqual([{ userId: memberId(1), change: { is_superadmin: true } }]);
  });

  it("test_admin_users_revoking_own_superadmin_refreshes_me", async () => {
    const store = setup();
    const user = userEvent.setup();
    await renderPage();
    const meCalls = countMeRequests();

    await confirmAction(
      user,
      "Remover Ana Teste dos superadministradores",
      "Remover Ana Teste dos superadministradores?",
      "Remover superadmin",
    );

    expect(await screen.findByText("Ana Teste não é mais superadministrador.")).toBeInTheDocument();
    expect(store.changes).toEqual([{ userId: USER_ID, change: { is_superadmin: false } }]);
    await waitFor(() => {
      expect(meCalls.length).toBeGreaterThan(0);
    });
  });

  it("test_admin_users_last_superadmin_error_is_shown", async () => {
    setup();
    server.use(updateUserFails(409, "last_superadmin"));
    const user = userEvent.setup();
    await renderPage();

    await confirmAction(
      user,
      "Remover Ana Teste dos superadministradores",
      "Remover Ana Teste dos superadministradores?",
      "Remover superadmin",
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "A instância precisa de ao menos um superadministrador ativo.",
    );
    expect(screen.queryByRole("status", { name: /não é mais/ })).not.toBeInTheDocument();
  });

  it("test_admin_users_cannot_suspend_self_error_is_shown", async () => {
    setup();
    server.use(updateUserFails(409, "cannot_suspend_self"));
    const user = userEvent.setup();
    await renderPage();

    await confirmAction(user, "Suspender Bruno Lima", "Suspender Bruno Lima?", "Suspender");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Você não pode suspender a própria conta.",
    );
  });
});
