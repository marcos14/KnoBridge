import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { Role } from "@/lib/api/auth";
import {
  makeMe,
  makeMember,
  makeMembers,
  makeWorkspace,
  memberId,
  OTHER_WORKSPACE_ID,
  USER_ID,
  WORKSPACE_ID,
} from "@/test/factories";
import {
  changeMemberRoleFails,
  meAs,
  membersAs,
  membersOk,
  membersRecorder,
  membersServerError,
  memberStore,
  removeMemberFails,
} from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

import { MembersPage } from "./MembersPage";

const PATH = `/w/${WORKSPACE_ID}/members`;

function asRole(role: Role) {
  server.use(meAs(makeMe({ workspaces: [makeWorkspace({ role })] })));
}

async function renderMembers() {
  const result = renderWithProviders({ path: PATH });
  await screen.findByRole("table", { name: "Membros do workspace" });
  return result;
}

function table() {
  return screen.getByRole("table", { name: "Membros do workspace" });
}

function rowOf(name: string): HTMLElement {
  const row = within(table())
    .getAllByRole("row")
    .find((item) => item.textContent.includes(name));
  if (row === undefined) {
    throw new Error(`No row for ${name}`);
  }
  return row;
}

function bodyRowTexts(): string[] {
  return within(table())
    .getAllByRole("row")
    .slice(1)
    .map((row) => row.textContent);
}

async function pickRole(user: ReturnType<typeof userEvent.setup>, name: string, role: string) {
  await user.click(screen.getByRole("combobox", { name: `Papel de ${name}` }));
  await user.click(await screen.findByRole("option", { name: role }));
}

describe("MembersList read-only", () => {
  it("test_members_list_viewer_reads_without_actions", async () => {
    asRole("viewer");
    await renderMembers();

    expect(screen.getByRole("heading", { level: 1, name: "Membros" })).toBeInTheDocument();
    expect(bodyRowTexts()).toHaveLength(4);
    expect(within(rowOf("Ana Teste")).getByText("Proprietário")).toBeInTheDocument();
    expect(within(rowOf("Ana Teste")).getByText("você")).toBeInTheDocument();
    expect(within(table()).queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Remover/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Ações" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Convidar" })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab")).not.toBeInTheDocument();
  });

  it("test_members_list_editor_reads_without_actions", async () => {
    asRole("editor");
    await renderMembers();

    expect(within(table()).queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Convidar" })).not.toBeInTheDocument();
  });

  it("test_members_list_renders_nothing_without_membership", () => {
    const { container } = renderWithProviders({
      routes: [{ path: "/w/:workspaceId/members", element: <MembersPage /> }],
      path: `/w/${OTHER_WORKSPACE_ID}/members`,
    });

    expect(container).toBeEmptyDOMElement();
  });
});

describe("MembersList search and paging", () => {
  it("test_members_list_searches_by_name_or_email_on_the_api", async () => {
    const user = userEvent.setup();
    const recorder = membersRecorder();
    server.use(recorder.handler);
    const { router } = await renderMembers();
    const search = screen.getByRole("searchbox", { name: "Buscar membros" });

    await user.type(search, "souza");

    await waitFor(() => {
      expect(bodyRowTexts()).toHaveLength(1);
    });
    expect(rowOf("Carla Souza")).toBeInTheDocument();
    expect(recorder.last()).toBe("query=souza&sort=name");
    expect(router.state.location.search).toBe("?q=souza");

    await user.clear(search);
    await user.type(search, "ninguém");

    expect(
      await within(table()).findByText("Nada encontrado com a busca e os filtros atuais."),
    ).toBeInTheDocument();
  });

  it("test_members_list_filters_by_role_and_sorts", async () => {
    const user = userEvent.setup();
    const recorder = membersRecorder();
    server.use(recorder.handler);
    const { router } = await renderMembers();

    await user.click(screen.getByRole("combobox", { name: "Papel" }));
    await user.click(await screen.findByRole("option", { name: "Administrador" }));
    await waitFor(() => {
      expect(recorder.last()).toBe("role=admin&sort=name");
    });

    await user.click(screen.getByRole("combobox", { name: "Ordenar por" }));
    await user.click(await screen.findByRole("option", { name: "Entrada mais recente" }));

    await waitFor(() => {
      expect(recorder.last()).toBe("role=admin&sort=-joined_at");
    });
    expect(router.state.location.search).toBe("?role=admin&sort=-joined_at");
  });

  it("test_members_list_pages_long_lists", async () => {
    const user = userEvent.setup();
    const many = Array.from({ length: 25 }, (_, index) =>
      makeMember({
        user_id: memberId(index),
        name: `Pessoa ${String(index).padStart(2, "0")}`,
        email: `pessoa${String(index)}@example.test`,
        role: "viewer",
      }),
    );
    server.use(membersAs(many));
    await renderMembers();
    const pagination = screen.getByRole("navigation", { name: "Paginação: Membros do workspace" });

    expect(pagination).toHaveTextContent("1–20 de 25");
    expect(bodyRowTexts()).toHaveLength(20);

    await user.click(within(pagination).getByRole("button", { name: "Próxima" }));

    await waitFor(() => {
      expect(pagination).toHaveTextContent("21–25 de 25");
    });
    expect(bodyRowTexts()[0]).toContain("Pessoa 20");
  });

  it("test_members_list_load_failure_offers_retry", async () => {
    const user = userEvent.setup();
    server.use(membersServerError);
    renderWithProviders({ path: PATH });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não foi possível carregar os membros.",
    );

    server.use(membersOk);
    await user.click(screen.getByRole("button", { name: "Tentar novamente" }));

    expect(await screen.findByRole("table", { name: "Membros do workspace" })).toBeInTheDocument();
  });

  it("test_members_list_shows_loading", () => {
    renderWithProviders({ path: PATH });

    return expect(screen.findByText("Carregando membros…")).resolves.toBeInTheDocument();
  });
});

describe("MembersList roles", () => {
  it("test_members_list_owner_changes_role", async () => {
    const user = userEvent.setup();
    const store = memberStore();
    server.use(...store.handlers);
    await renderMembers();

    await pickRole(user, "Carla Souza", "Administrador");

    expect(await screen.findByText("O papel de Carla Souza agora é administrador.")).toHaveRole(
      "status",
    );
    expect(store.changes).toEqual([{ userId: memberId(2), role: "admin" }]);
    await waitFor(() => {
      expect(screen.getByRole("combobox", { name: "Papel de Carla Souza" })).toHaveTextContent(
        "Administrador",
      );
    });
  });

  it("test_members_list_admin_cannot_grant_or_manage_owner", async () => {
    const user = userEvent.setup();
    asRole("admin");
    await renderMembers();

    expect(within(rowOf("Ana Teste")).queryByRole("combobox")).not.toBeInTheDocument();
    expect(within(rowOf("Ana Teste")).queryByRole("button")).not.toBeInTheDocument();
    expect(within(rowOf("Ana Teste")).getByText("Proprietário")).toBeInTheDocument();

    await user.click(screen.getByRole("combobox", { name: "Papel de Carla Souza" }));

    expect(await screen.findByRole("option", { name: "Proprietário" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    expect(screen.getByRole("option", { name: "Administrador" })).not.toHaveAttribute(
      "aria-disabled",
    );
  });

  it("test_members_list_shows_last_owner_error", async () => {
    const user = userEvent.setup();
    await renderMembers();
    server.use(changeMemberRoleFails(409, "last_owner"));

    await pickRole(user, "Ana Teste", "Administrador");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "O workspace precisa de ao menos um proprietário.",
    );
  });

  it("test_members_list_shows_role_not_allowed_error", async () => {
    const user = userEvent.setup();
    asRole("admin");
    await renderMembers();
    server.use(changeMemberRoleFails(403, "role_not_allowed"));

    await pickRole(user, "Davi Rocha", "Editor");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Seu papel não permite atribuir este papel nem gerenciar quem o tem.",
    );
  });
});

describe("MembersList removal", () => {
  it("test_members_list_removes_member_after_confirmation", async () => {
    const user = userEvent.setup();
    const store = memberStore();
    server.use(...store.handlers);
    await renderMembers();

    await user.click(screen.getByRole("button", { name: "Remover Carla Souza" }));
    const dialog = await screen.findByRole("alertdialog", {
      name: "Remover Carla Souza do workspace?",
    });
    expect(store.removed).toEqual([]);
    await user.click(within(dialog).getByRole("button", { name: "Remover" }));

    expect(await screen.findByText("Carla Souza foi removido do workspace.")).toHaveRole("status");
    expect(store.removed).toEqual([memberId(2)]);
    await waitFor(() => {
      expect(bodyRowTexts()).toHaveLength(3);
    });
  });

  it("test_members_list_cancel_keeps_member", async () => {
    const user = userEvent.setup();
    const store = memberStore();
    server.use(...store.handlers);
    await renderMembers();

    await user.click(screen.getByRole("button", { name: "Remover Davi Rocha" }));
    await user.click(await screen.findByRole("button", { name: "Cancelar" }));

    expect(store.removed).toEqual([]);
    expect(bodyRowTexts()).toHaveLength(4);
  });

  it("test_members_list_removal_error_is_shown", async () => {
    const user = userEvent.setup();
    await renderMembers();
    server.use(removeMemberFails(409, "last_owner"));

    await user.click(screen.getByRole("button", { name: "Remover Bruno Lima" }));
    await user.click(await screen.findByRole("button", { name: "Remover" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "O workspace precisa de ao menos um proprietário.",
    );
  });

  it("test_members_list_leaving_goes_to_another_workspace", async () => {
    const user = userEvent.setup();
    const store = memberStore([
      ...makeMembers(),
      makeMember({ user_id: memberId(9), name: "Zeca Dono", role: "owner" }),
    ]);
    server.use(
      ...store.handlers,
      meAs(
        makeMe({
          workspaces: [makeWorkspace(), makeWorkspace({ id: OTHER_WORKSPACE_ID, name: "Outro" })],
        }),
      ),
    );
    const { router } = await renderMembers();

    await user.click(within(rowOf("Ana Teste")).getByRole("button", { name: "Sair do workspace" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Sair do workspace?" });
    server.use(
      meAs(makeMe({ workspaces: [makeWorkspace({ id: OTHER_WORKSPACE_ID, name: "Outro" })] })),
    );
    await user.click(within(dialog).getByRole("button", { name: "Sair do workspace" }));

    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/w/${OTHER_WORKSPACE_ID}`);
    });
    expect(store.removed).toEqual([USER_ID]);
  });
});
