import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import type { Role } from "@/lib/api/auth";
import {
  makeMe,
  makeWorkspace,
  memberId,
  PRODUCT_ID,
  USER_ID,
  WORKSPACE_ID,
} from "@/test/factories";
import {
  meAs,
  memberLevelsAs,
  memberLevelsServerError,
  memberLevelStore,
  setMemberLevelFails,
} from "@/test/handlers";
import { makeMemberLevels, makeProductRefs } from "@/test/levelFactories";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

const PATH = `/w/${WORKSPACE_ID}/members`;
const TABLE = "Níveis dos membros por produto";

type User = ReturnType<typeof userEvent.setup>;

function asRole(role: Role) {
  server.use(meAs(makeMe({ workspaces: [makeWorkspace({ role })] })));
}

async function openLevels(user: User) {
  const result = renderWithProviders({ path: PATH });
  await user.click(await screen.findByRole("tab", { name: "Níveis por produto" }));
  return result;
}

function cell(name: string, product: string) {
  return screen.getByRole("combobox", { name: `Nível de ${name} em ${product}` });
}

async function pickLevel(user: User, name: string, product: string, option: string) {
  await user.click(cell(name, product));
  await user.click(await screen.findByRole("option", { name: option }));
}

describe("MemberLevelsList", () => {
  it("test_member_levels_show_stored_levels_and_the_default_of_each_role", async () => {
    const user = userEvent.setup();
    await openLevels(user);

    const table = await screen.findByRole("table", { name: TABLE });
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map((header) => header.textContent),
    ).toEqual(["Nome", "Rascunho (inativo)", "Suporte ERP"]);
    expect(cell("Carla Souza", "Suporte ERP")).toHaveTextContent("Suporte");
    expect(cell("Carla Souza", "Rascunho")).toHaveTextContent("Padrão do papel: Usuário final");
    expect(cell("Bruno Lima", "Suporte ERP")).toHaveTextContent(
      "Padrão do papel: Desenvolvimento e produto",
    );
    expect(within(table).getByText("Leitor")).toBeVisible();
  });

  it("test_member_levels_owner_raises_a_member_in_one_product", async () => {
    const user = userEvent.setup();
    const store = memberLevelStore();
    server.use(...store.handlers);
    await openLevels(user);
    await screen.findByRole("table", { name: TABLE });

    await pickLevel(user, "Davi Rocha", "Suporte ERP", "Suporte");

    expect(
      await screen.findByText("Davi Rocha agora responde até Suporte em Suporte ERP."),
    ).toHaveRole("status");
    expect(store.changes).toEqual([
      {
        userId: memberId(3),
        body: { levels: [{ product_id: PRODUCT_ID, max_level: "support" }] },
      },
    ]);
    await waitFor(() => {
      expect(cell("Davi Rocha", "Suporte ERP")).toHaveTextContent("Suporte");
    });
  });

  it("test_member_levels_back_to_the_default_drops_the_stored_level", async () => {
    const user = userEvent.setup();
    const store = memberLevelStore();
    server.use(...store.handlers);
    await openLevels(user);
    await screen.findByRole("table", { name: TABLE });

    await pickLevel(user, "Carla Souza", "Suporte ERP", "Padrão do papel: Usuário final");

    expect(
      await screen.findByText("Carla Souza voltou ao padrão do papel em Suporte ERP."),
    ).toBeVisible();
    expect(store.changes[0]?.body).toEqual({
      levels: [{ product_id: PRODUCT_ID, max_level: null }],
    });
  });

  it("test_member_levels_own_change_reloads_me", async () => {
    const user = userEvent.setup();
    const store = memberLevelStore();
    let meReads = 0;
    server.use(
      ...store.handlers,
      http.get("*/v1/me", () => {
        meReads += 1;
        return HttpResponse.json(makeMe());
      }),
    );
    await openLevels(user);
    await screen.findByRole("table", { name: TABLE });
    const before = meReads;

    await pickLevel(user, "Ana Teste", "Suporte ERP", "Suporte");

    await screen.findByText("Ana Teste agora responde até Suporte em Suporte ERP.");
    expect(store.changes[0]?.userId).toBe(USER_ID);
    await waitFor(() => {
      expect(meReads).toBeGreaterThan(before);
    });
  });

  it("test_member_levels_search_by_name_goes_to_the_api", async () => {
    const user = userEvent.setup();
    const store = memberLevelStore();
    server.use(...store.handlers);
    await openLevels(user);
    await screen.findByRole("table", { name: TABLE });

    await user.type(screen.getByRole("searchbox", { name: "Buscar membros" }), "carla");

    await waitFor(() => {
      expect(store.queries.at(-1)?.get("query")).toBe("carla");
    });
    await waitFor(() => {
      expect(screen.queryByRole("combobox", { name: /Nível de Bruno Lima/ })).toBeNull();
    });
    expect(cell("Carla Souza", "Suporte ERP")).toBeVisible();
  });

  it("test_member_levels_admin_cannot_edit_the_owner", async () => {
    const user = userEvent.setup();
    asRole("admin");
    await openLevels(user);
    await screen.findByRole("table", { name: TABLE });

    expect(cell("Ana Teste", "Suporte ERP")).toBeDisabled();
    expect(cell("Bruno Lima", "Suporte ERP")).toBeEnabled();
  });

  it("test_member_levels_tab_is_only_for_owners_and_admins", async () => {
    asRole("editor");
    renderWithProviders({ path: PATH });

    await screen.findByRole("table", { name: "Membros do workspace" });
    expect(screen.queryByRole("tab", { name: "Níveis por produto" })).not.toBeInTheDocument();
  });

  it("test_member_levels_show_the_error_of_a_refused_change", async () => {
    const user = userEvent.setup();
    server.use(setMemberLevelFails(403, "role_not_allowed"));
    await openLevels(user);
    await screen.findByRole("table", { name: TABLE });

    await pickLevel(user, "Davi Rocha", "Rascunho", "Suporte");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Seu papel não permite atribuir este papel nem gerenciar quem o tem.",
    );
  });

  it("test_member_levels_without_products_explain_where_they_come_from", async () => {
    const user = userEvent.setup();
    server.use(memberLevelsAs(makeMemberLevels([]), []));
    await openLevels(user);

    expect(await screen.findByText(/Nenhum produto cadastrado ainda/)).toBeVisible();
    expect(screen.queryByRole("table", { name: TABLE })).not.toBeInTheDocument();
  });

  it("test_member_levels_failure_offers_a_retry", async () => {
    const user = userEvent.setup();
    server.use(memberLevelsServerError);
    await openLevels(user);

    expect(await screen.findByText("Não foi possível carregar os níveis.")).toHaveRole("alert");
    server.use(memberLevelsAs());
    await user.click(screen.getByRole("button", { name: "Tentar novamente" }));

    expect(await screen.findByRole("table", { name: TABLE })).toBeVisible();
  });

  it("test_member_levels_search_and_role_go_to_the_api", async () => {
    const user = userEvent.setup();
    const store = memberLevelStore();
    server.use(...store.handlers);
    const { router } = await openLevels(user);
    await screen.findByRole("table", { name: TABLE });

    await user.click(screen.getByRole("combobox", { name: "Papel" }));
    await user.click(await screen.findByRole("option", { name: "Editor" }));

    await waitFor(() => {
      expect(store.queries.at(-1)?.get("role")).toBe("editor");
    });
    expect(router.state.location.search).toBe("?role=editor");
    await waitFor(() => {
      expect(screen.queryByRole("combobox", { name: /Nível de Davi Rocha/ })).toBeNull();
    });
  });

  it("test_member_levels_leave_a_cell_empty_when_the_api_omits_a_product", async () => {
    const user = userEvent.setup();
    const [first] = makeMemberLevels();
    server.use(
      memberLevelsAs(
        // A member whose row lacks the second product (a product created meanwhile).
        first === undefined ? [] : [{ ...first, levels: first.levels.slice(0, 1) }],
        makeProductRefs(),
      ),
    );
    await openLevels(user);
    await screen.findByRole("table", { name: TABLE });

    expect(cell("Ana Teste", "Rascunho")).toBeVisible();
    expect(
      screen.queryByRole("combobox", { name: "Nível de Ana Teste em Suporte ERP" }),
    ).not.toBeInTheDocument();
  });
});
