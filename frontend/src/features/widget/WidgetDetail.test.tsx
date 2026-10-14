import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it } from "vitest";

import { makeProduct, PRODUCT_ID, WORKSPACE_ID } from "@/test/factories";
import {
  productsAs,
  widgetActionFails,
  widgetServerError,
  widgetsAs,
  widgetStore,
} from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";
import { makeWidget, OTHER_WIDGET_ID, WIDGET_ID, WIDGET_SECRET } from "@/test/widgetFactories";

import { installSnippet } from "./installSnippets";
import { WIDGET_ELEMENT, WIDGET_SCRIPT_ID } from "./previewElement";

const LIST = `/w/${WORKSPACE_ID}/widgets`;
const NEW = `${LIST}/new`;
const DETAIL = `${LIST}/${WIDGET_ID}`;
const NEW_WIDGET_ID = "00000000-0000-4000-8000-000000000901";

type User = ReturnType<typeof userEvent.setup>;

// The real element comes from the instance's script, which jsdom never loads: a stand-in with
// the same tag lets the test see what the preview builds.
beforeAll(() => {
  if (customElements.get(WIDGET_ELEMENT) === undefined) {
    customElements.define(WIDGET_ELEMENT, class extends HTMLElement {});
  }
});

afterEach(() => {
  document.getElementById(WIDGET_SCRIPT_ID)?.remove();
});

function useStore(widgets = [makeWidget()]) {
  const store = widgetStore(widgets);
  server.use(...store.handlers);
  return store;
}

async function renderDetail(path = DETAIL) {
  const user = userEvent.setup();
  const result = renderWithProviders({ path });
  await screen.findByRole("form", { name: "Configuração do widget" });
  return { user, ...result };
}

/** The `<knobridge-chat>` inside the preview area (it has no role or text of its own). */
function previewElement(): HTMLElement {
  const element = screen
    .getByRole("region", { name: "Prévia do widget" })
    .querySelector<HTMLElement>(WIDGET_ELEMENT);
  if (element === null) {
    throw new Error("No widget element in the preview");
  }
  return element;
}

async function save(user: User, name = "Salvar alterações") {
  await user.click(screen.getByRole("button", { name }));
}

describe("WidgetDetail create", () => {
  it("test_create_widget_sends_the_form_and_opens_the_new_widget", async () => {
    const store = useStore([]);
    const { user, router } = await renderDetail(NEW);

    expect(screen.getByRole("heading", { level: 1, name: "Novo widget" })).toBeVisible();
    expect(screen.queryByRole("region", { name: "Prévia do widget" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("combobox", { name: "Produto" }));
    await user.click(await screen.findByRole("option", { name: "Suporte ERP" }));
    await user.type(screen.getByRole("textbox", { name: "Nome" }), "Site novo");
    await user.type(
      screen.getByRole("textbox", { name: "Origens, uma por linha" }),
      "https://App.cliente.com.br{Enter}https://*.cliente.com.br",
    );
    await save(user, "Criar widget");

    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`${LIST}/${NEW_WIDGET_ID}`);
    });
    expect(await screen.findByRole("heading", { level: 1, name: "Site novo" })).toBeVisible();
    expect(
      screen.getByText("Widget Site novo criado. Copie o trecho abaixo para o seu site."),
    ).toBeVisible();
    expect(store.created).toEqual([
      expect.objectContaining({
        product_id: PRODUCT_ID,
        name: "Site novo",
        allowed_origins: ["https://App.cliente.com.br", "https://*.cliente.com.br"],
        mode: "bubble",
        messages_per_day: 1000,
      }),
    ]);
  });

  it("test_create_widget_validates_product_name_and_origins_before_sending", async () => {
    const store = useStore([]);
    const { user } = await renderDetail(NEW);

    await user.type(
      screen.getByRole("textbox", { name: "Origens, uma por linha" }),
      "https://a.com/app{Enter}ftp://b.com",
    );
    await save(user, "Criar widget");

    expect(await screen.findByText("Escolha o produto do widget.")).toBeVisible();
    expect(screen.getByText("Informe o nome do widget.")).toBeVisible();
    expect(
      screen.getByText(
        "https://a.com/app: tire o caminho, a consulta e a barra final. ftp://b.com: use http ou https.",
      ),
    ).toBeVisible();
    expect(store.created).toEqual([]);
  });

  it("test_create_widget_shows_the_origins_the_api_refused", async () => {
    server.use(
      widgetActionFails("create", 422, "widget_origin_invalid", {
        origins: [{ origin: "https://b.com", reason: "duplicate" }],
      }),
    );
    const { user } = await renderDetail(NEW);

    await user.click(screen.getByRole("combobox", { name: "Produto" }));
    await user.click(await screen.findByRole("option", { name: "Suporte ERP" }));
    await user.type(screen.getByRole("textbox", { name: "Nome" }), "Site");
    await user.type(
      screen.getByRole("textbox", { name: "Origens, uma por linha" }),
      "https://b.com",
    );
    await save(user, "Criar widget");

    expect(await screen.findByText("https://b.com: repetida.")).toBeVisible();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Algum domínio permitido é inválido. Confira os apontados no campo.",
    );
  });

  it("test_create_widget_with_a_taken_name_says_so", async () => {
    useStore([makeWidget()]);
    const { user } = await renderDetail(NEW);

    await user.click(screen.getByRole("combobox", { name: "Produto" }));
    await user.click(await screen.findByRole("option", { name: "Suporte ERP" }));
    await user.type(screen.getByRole("textbox", { name: "Nome" }), "Site público");
    await user.type(
      screen.getByRole("textbox", { name: "Origens, uma por linha" }),
      "https://b.com",
    );
    await save(user, "Criar widget");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Já existe um widget com esse nome no workspace.",
    );
  });

  it("test_create_widget_with_a_ticket_webhook_says_the_button_uses_it", async () => {
    server.use(productsAs([makeProduct({ ticket_webhook_configured: true })]));
    const { user } = await renderDetail(NEW);

    expect(screen.getByText(/ainda não tem o webhook de chamados/)).toBeVisible();
    await user.click(screen.getByRole("combobox", { name: "Produto" }));
    await user.click(await screen.findByRole("option", { name: "Suporte ERP" }));

    expect(screen.getByText("Usa o webhook de chamados do produto.")).toBeVisible();
  });

  it("test_create_widget_marks_inactive_products", async () => {
    const { user } = await renderDetail(NEW);

    await user.click(screen.getByRole("combobox", { name: "Produto" }));

    expect(await screen.findByRole("option", { name: "Rascunho (inativo)" })).toBeVisible();
  });
});

describe("WidgetDetail edit", () => {
  it("test_edit_widget_sends_only_what_changed", async () => {
    const store = useStore();
    const { user } = await renderDetail();

    expect(screen.getByText("Produto: Suporte ERP (não muda depois de criado).")).toBeVisible();
    const greeting = screen.getByRole("textbox", { name: "Saudação" });
    await user.clear(greeting);
    await user.type(greeting, "Oi!");
    await user.click(screen.getByRole("radio", { name: "Escuro" }));
    await user.click(screen.getByRole("checkbox", { name: "Avaliação das respostas (👍/👎)" }));
    await save(user);

    expect(await screen.findByText("Alterações salvas.")).toBeVisible();
    expect(store.changes).toEqual([
      {
        widgetId: WIDGET_ID,
        body: { theme: "dark", greeting: "Oi!", feedback_enabled: false },
      },
    ]);
  });

  it("test_edit_widget_without_changes_sends_nothing", async () => {
    const store = useStore();
    const { user } = await renderDetail();

    await save(user);

    expect(await screen.findByText("Nada mudou.")).toBeVisible();
    expect(store.changes).toEqual([]);
  });

  it("test_edit_widget_inline_mode_disables_the_position", async () => {
    const { user } = await renderDetail();

    expect(screen.getByRole("radio", { name: "Canto inferior esquerdo" })).toBeEnabled();
    await user.click(screen.getByRole("radio", { name: "Embutido" }));

    expect(screen.getByRole("radio", { name: "Canto inferior esquerdo" })).toBeDisabled();
    expect(screen.getByText("A posição só vale no modo balão.")).toBeVisible();
  });

  it("test_edit_widget_warns_about_a_low_contrast_color", async () => {
    const { user } = await renderDetail();
    const color = screen.getByRole("textbox", { name: "Cor principal" });

    await user.clear(color);
    await user.type(color, "#ffff00");

    expect(screen.getByText(/contraste abaixo de 3:1 com o fundo no tema Claro/)).toBeVisible();
    fireEvent.change(screen.getByLabelText("Escolher a cor principal"), {
      target: { value: "#3b82f6" },
    });
    expect(color).toHaveValue("#3b82f6");
    expect(screen.queryByText(/contraste abaixo de 3:1/)).not.toBeInTheDocument();
  });

  it("test_edit_widget_refuses_limits_out_of_range", async () => {
    const store = useStore();
    const { user } = await renderDetail();
    const limit = screen.getByRole("textbox", { name: "Perguntas por visitante (IP) por hora" });

    await user.clear(limit);
    await user.type(limit, "5000");
    await save(user);

    expect(await screen.findByText("Use um número inteiro de 1 a 1000.")).toBeVisible();
    expect(store.changes).toEqual([]);
  });

  it("test_edit_widget_shows_a_failed_save", async () => {
    server.use(widgetActionFails("update", 500, "internal_error"));
    const { user } = await renderDetail();

    await user.type(screen.getByRole("textbox", { name: "Título" }), "Ajuda");
    await save(user);

    expect(await screen.findByRole("alert")).toBeVisible();
  });

  it("test_widget_detail_not_found", async () => {
    renderWithProviders({ path: `${LIST}/00000000-0000-4000-8000-00000000dead` });

    expect(
      await screen.findByRole("heading", { level: 1, name: "Widget não encontrado" }),
    ).toBeVisible();
    expect(screen.getByRole("link", { name: "Voltar para os widgets" })).toHaveAttribute(
      "href",
      LIST,
    );
  });

  it("test_widget_detail_retries_after_load_failure", async () => {
    server.use(widgetServerError);
    const user = userEvent.setup();
    renderWithProviders({ path: DETAIL });

    expect(await screen.findByText("Não foi possível carregar o widget.")).toBeVisible();
    server.use(...widgetsAs());
    await user.click(screen.getByRole("button", { name: "Tentar novamente" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Site público" })).toBeVisible();
  });
});

describe("WidgetDetail install", () => {
  it("test_widget_install_snippet_is_copied", async () => {
    const { user } = await renderDetail();
    const expected = installSnippet(
      window.location.origin,
      "kbp_3k9x2m4q7w8e1r5t6y0u2i4o",
      "bubble",
    );

    expect(
      screen.getByText(/<knobridge-chat widget-key="kbp_3k9x2m4q7w8e1r5t6y0u2i4o">/),
    ).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Copiar o trecho" }));

    expect(await navigator.clipboard.readText()).toBe(expected);
    expect(expected).toContain(`${window.location.origin}/widget/v1/knobridge-chat.js`);
  });

  it("test_widget_install_snippet_of_an_inactive_inline_widget", async () => {
    server.use(...widgetsAs([makeWidget({ mode: "inline", active: false })]));
    await renderDetail();

    expect(screen.getByText(/mode="inline" style="height: 600px"/)).toBeVisible();
    expect(
      screen.getByText("O widget está desativado: o trecho só funciona depois de ativá-lo."),
    ).toBeVisible();
  });
});

describe("WidgetDetail preview", () => {
  it("test_widget_preview_loads_the_instance_script_once_and_builds_the_element", async () => {
    const { user, router } = await renderDetail();

    const scripts = document.querySelectorAll(`script#${WIDGET_SCRIPT_ID}`);
    expect(scripts).toHaveLength(1);
    expect(scripts[0]).toHaveAttribute(
      "src",
      `${window.location.origin}/widget/v1/knobridge-chat.js`,
    );
    const element = previewElement();
    expect(element).toHaveAttribute("widget-key", "kbp_3k9x2m4q7w8e1r5t6y0u2i4o");
    expect(element).toHaveAttribute("mode", "inline");
    expect(element).toHaveAttribute("api-base", window.location.origin);
    expect(element).toHaveAttribute("primary-color", "#2563eb");
    expect(element).not.toHaveAttribute("title");
    expect(
      screen.getByText(/A prévia conversa de verdade: as perguntas ficam gravadas/),
    ).toBeVisible();

    await user.click(screen.getByRole("link", { name: "Voltar para os widgets" }));
    await screen.findByRole("table", { name: "Widgets do workspace" });
    await router.navigate(`${LIST}/${OTHER_WIDGET_ID}`);
    await screen.findByRole("form", { name: "Configuração do widget" });

    expect(document.querySelectorAll(`script#${WIDGET_SCRIPT_ID}`)).toHaveLength(1);
    expect(previewElement()).toHaveAttribute("widget-key", "kbp_portal0interno0000000000");
    expect(previewElement()).toHaveAttribute("theme", "dark");
  });

  it("test_widget_preview_follows_the_unsaved_appearance", async () => {
    const { user } = await renderDetail();
    const element = previewElement();

    await user.type(screen.getByRole("textbox", { name: "Título" }), "Ajuda do ERP");
    await user.clear(screen.getByRole("textbox", { name: "Saudação" }));
    await user.click(screen.getByRole("radio", { name: "Claro" }));

    expect(previewElement()).toBe(element);
    expect(element).toHaveAttribute("title", "Ajuda do ERP");
    expect(element).toHaveAttribute("greeting", "");
    expect(element).toHaveAttribute("theme", "light");
  });
});

describe("WidgetDetail signing secret", () => {
  it("test_signing_secret_is_shown_once_and_copied", async () => {
    const store = useStore();
    const { user } = await renderDetail();

    expect(
      screen.getByText("Nenhum segredo gerado: todos os visitantes são anônimos."),
    ).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Gerar segredo" }));

    expect(await screen.findByLabelText("Segredo de assinatura")).toHaveTextContent(WIDGET_SECRET);
    await user.click(screen.getByRole("button", { name: "Copiar o segredo" }));
    expect(await navigator.clipboard.readText()).toBe(WIDGET_SECRET);
    expect(store.rotations).toEqual([WIDGET_ID]);
    expect(await screen.findByText(/Segredo gerado em/)).toBeVisible();
    expect(screen.getByRole("button", { name: "Substituir segredo" })).toBeVisible();
  });

  it("test_signing_secret_rotation_asks_for_confirmation", async () => {
    const store = useStore([makeWidget({ signing_secret_configured: true })]);
    const { user } = await renderDetail();

    await user.click(screen.getByRole("button", { name: "Substituir segredo" }));
    const dialog = await screen.findByRole("alertdialog", {
      name: "Substituir o segredo de assinatura?",
    });
    expect(dialog).toHaveTextContent("passam a ser recusadas na hora");
    await user.click(within(dialog).getByRole("button", { name: "Substituir segredo" }));

    expect(await screen.findByLabelText("Segredo de assinatura")).toHaveTextContent(WIDGET_SECRET);
    expect(store.rotations).toEqual([WIDGET_ID]);
  });

  it("test_signing_secret_removal_asks_for_confirmation", async () => {
    const store = useStore([
      makeWidget({
        signing_secret_configured: true,
        signing_secret_created_at: "2026-10-06T09:00:00Z",
      }),
    ]);
    const { user } = await renderDetail();

    expect(screen.getByText(/Segredo gerado em/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Remover segredo" }));
    await user.click(
      within(
        await screen.findByRole("alertdialog", { name: "Remover o segredo de assinatura?" }),
      ).getByRole("button", { name: "Remover segredo" }),
    );

    expect(
      await screen.findByText("Segredo removido: os visitantes passam a ser anônimos."),
    ).toBeVisible();
    expect(store.removals).toEqual([WIDGET_ID]);
    expect(await screen.findByRole("button", { name: "Gerar segredo" })).toBeVisible();
  });

  it("test_signing_secret_failure_is_shown", async () => {
    server.use(widgetActionFails("rotateSecret", 500, "internal_error"));
    const { user } = await renderDetail();

    await user.click(screen.getByRole("button", { name: "Gerar segredo" }));

    expect(await screen.findByRole("alert")).toBeVisible();
    expect(screen.queryByLabelText("Segredo de assinatura")).not.toBeInTheDocument();
  });

  it("test_signing_examples_read_the_secret_from_the_environment", async () => {
    const { user } = await renderDetail();

    await user.click(screen.getByRole("button", { name: "Copiar o código Python" }));
    const python = await navigator.clipboard.readText();
    expect(python).toContain('os.environ["KNOBRIDGE_WIDGET_SIGNING_SECRET"]');
    await user.click(screen.getByRole("button", { name: "Copiar o elemento" }));
    expect(await navigator.clipboard.readText()).toContain(
      'widget-key="kbp_3k9x2m4q7w8e1r5t6y0u2i4o" identity=',
    );
  });
});
