import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { Role } from "@/lib/api/auth";
import {
  makeMe,
  makeWorkspace,
  OTHER_PRODUCT_ID,
  OTHER_WORKSPACE_ID,
  WORKSPACE_ID,
} from "@/test/factories";
import {
  meAs,
  productsAs,
  widgetActionFails,
  widgetsAs,
  widgetsServerError,
  widgetStore,
} from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";
import { makeWidget, OTHER_WIDGET_ID, WIDGET_ID } from "@/test/widgetFactories";

import { WidgetsPage } from "./WidgetsPage";

const PATH = `/w/${WORKSPACE_ID}/widgets`;
const TABLE = "Widgets do workspace";

function asRole(role: Role) {
  server.use(meAs(makeMe({ workspaces: [makeWorkspace({ role })] })));
}

async function renderWidgets(path = PATH) {
  const result = renderWithProviders({ path });
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

describe("WidgetsPage list", () => {
  it("test_widgets_page_lists_key_product_origins_mode_and_state", async () => {
    await renderWidgets();

    const site = rowOf("Site público");
    expect(within(site).getByText("kbp_3k9x2m4q7w8e1r5t6y0u2i4o")).toBeInTheDocument();
    expect(within(site).getByText("Suporte ERP")).toBeInTheDocument();
    expect(within(site).getByText("https://*.cliente.com.br")).toBeInTheDocument();
    expect(within(site).getByText("Balão")).toBeInTheDocument();
    expect(within(site).getByText("Ativo")).toBeInTheDocument();
    expect(within(site).getByRole("link", { name: "Configurar Site público" })).toHaveAttribute(
      "href",
      `${PATH}/${WIDGET_ID}`,
    );

    const portal = rowOf("Portal interno");
    expect(within(portal).getByText("+1 domínio")).toBeInTheDocument();
    expect(within(portal).getByText("Embutido")).toBeInTheDocument();
    expect(within(portal).getByText("Inativo")).toBeInTheDocument();
  });

  it("test_widgets_page_searches_and_filters_in_the_api", async () => {
    const store = widgetStore();
    server.use(...store.handlers);
    await renderWidgets(`${PATH}?q=site&product=${OTHER_PRODUCT_ID}&active=false`);

    const query = store.listQueries.at(-1);
    expect(query?.get("query")).toBe("site");
    expect(query?.get("product_id")).toBe(OTHER_PRODUCT_ID);
    expect(query?.get("active")).toBe("false");
    expect(screen.getByText("Nada encontrado com a busca e os filtros atuais.")).toBeVisible();
  });

  it("test_widgets_page_filter_keeps_a_product_not_listed", async () => {
    const unknown = "00000000-0000-4000-8000-00000000dead";
    await renderWidgets(`${PATH}?product=${unknown}`);

    expect(screen.getByRole("combobox", { name: "Produto" })).toHaveTextContent(
      `Produto ${unknown}`,
    );
  });

  it("test_widgets_page_filters_by_product_from_the_select", async () => {
    const user = userEvent.setup();
    const store = widgetStore();
    server.use(...store.handlers);
    const { router } = await renderWidgets();

    await user.click(screen.getByRole("combobox", { name: "Produto" }));
    await user.click(await screen.findByRole("option", { name: "Rascunho" }));
    await user.click(screen.getByRole("combobox", { name: "Estado" }));
    await user.click(await screen.findByRole("option", { name: "Inativo" }));

    await waitFor(() => {
      expect(router.state.location.search).toBe(`?product=${OTHER_PRODUCT_ID}&active=false`);
    });
  });

  it("test_widgets_page_empty_points_to_creating_one", async () => {
    server.use(...widgetsAs([]));
    await renderWidgets();

    expect(
      screen.getByText(
        "Nenhum widget ainda. Crie um para conversar com os visitantes do seu site.",
      ),
    ).toBeVisible();
    expect(screen.getByRole("link", { name: "Criar o primeiro widget" })).toHaveAttribute(
      "href",
      `${PATH}/new`,
    );
  });

  it("test_widgets_page_empty_without_products_points_to_products", async () => {
    server.use(...widgetsAs([]), productsAs([]));
    await renderWidgets();

    expect(await screen.findByRole("link", { name: "Ir para Produtos" })).toHaveAttribute(
      "href",
      `/w/${WORKSPACE_ID}/products`,
    );
  });

  it("test_widgets_page_retries_after_load_failure", async () => {
    const user = userEvent.setup();
    server.use(widgetsServerError);
    renderWithProviders({ path: PATH });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não foi possível carregar os widgets.",
    );
    server.use(...widgetsAs());
    await user.click(screen.getByRole("button", { name: "Tentar novamente" }));

    expect(await screen.findByRole("table", { name: TABLE })).toBeInTheDocument();
  });

  it("test_widgets_page_renders_title_outside_a_membership", async () => {
    renderWithProviders({
      path: `/w/${OTHER_WORKSPACE_ID}/widgets`,
      routes: [{ path: "/w/:workspaceId/widgets", element: <WidgetsPage /> }],
    });

    expect(await screen.findByRole("heading", { level: 1, name: "Widgets" })).toBeVisible();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});

describe("WidgetsPage roles", () => {
  it.each(["editor", "viewer"] as const)("test_widgets_page_%s_gets_forbidden", async (role) => {
    asRole(role);
    renderWithProviders({ path: PATH });

    expect(
      await screen.findByRole("heading", { level: 1, name: "Acesso negado" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Widgets" })).not.toBeInTheDocument();
  });

  it.each(["admin", "owner"] as const)("test_widgets_page_%s_sees_the_menu_item", async (role) => {
    asRole(role);
    await renderWidgets();

    expect(screen.getByRole("link", { name: "Widgets" })).toHaveAttribute("href", PATH);
    expect(screen.getByRole("link", { name: "Novo widget" })).toHaveAttribute(
      "href",
      `${PATH}/new`,
    );
  });
});

describe("WidgetsPage actions", () => {
  it("test_widgets_page_deactivates_and_activates_a_widget", async () => {
    const user = userEvent.setup();
    const store = widgetStore();
    server.use(...store.handlers);
    await renderWidgets();

    await user.click(screen.getByRole("button", { name: "Desativar Site público" }));
    expect(
      await screen.findByText(
        "Widget Site público desativado: o chat some do site até ser ativado de novo.",
      ),
    ).toBeVisible();
    await user.click(await screen.findByRole("button", { name: "Ativar Site público" }));

    expect(await screen.findByText("Widget Site público ativado.")).toBeVisible();
    expect(store.changes).toEqual([
      { widgetId: WIDGET_ID, body: { active: false } },
      { widgetId: WIDGET_ID, body: { active: true } },
    ]);
  });

  it("test_widgets_page_delete_warns_that_conversations_go_too", async () => {
    const user = userEvent.setup();
    const store = widgetStore();
    server.use(...store.handlers);
    await renderWidgets();

    await user.click(screen.getByRole("button", { name: "Excluir Portal interno" }));
    const dialog = await screen.findByRole("alertdialog", {
      name: "Excluir o widget Portal interno?",
    });
    expect(dialog).toHaveTextContent("As conversas dos visitantes deste widget");
    await user.click(within(dialog).getByRole("button", { name: "Excluir" }));

    expect(await screen.findByText("Widget Portal interno excluído.")).toBeVisible();
    expect(store.deleted).toEqual([OTHER_WIDGET_ID]);
    await waitFor(() => {
      expect(screen.queryByText("kbp_portal0interno0000000000")).not.toBeInTheDocument();
    });
  });

  it("test_widgets_page_delete_cancelled_keeps_the_widget", async () => {
    const user = userEvent.setup();
    const store = widgetStore();
    server.use(...store.handlers);
    await renderWidgets();

    await user.click(screen.getByRole("button", { name: "Excluir Site público" }));
    await user.click(await screen.findByRole("button", { name: "Cancelar" }));

    expect(store.deleted).toEqual([]);
    expect(rowOf("Site público")).toBeInTheDocument();
  });

  it("test_widgets_page_shows_a_failed_action", async () => {
    const user = userEvent.setup();
    server.use(widgetActionFails("update", 500, "internal_error"));
    server.use(...widgetsAs([makeWidget()]));
    await renderWidgets();

    await user.click(screen.getByRole("button", { name: "Desativar Site público" }));

    expect(await screen.findByRole("alert")).toBeVisible();
  });

  it("test_widgets_page_shows_a_failed_delete", async () => {
    const user = userEvent.setup();
    server.use(widgetActionFails("delete", 404, "not_found"));
    await renderWidgets();

    await user.click(screen.getByRole("button", { name: "Excluir Site público" }));
    await user.click(await screen.findByRole("button", { name: "Excluir" }));

    expect(await screen.findByRole("alert")).toBeVisible();
  });
});
