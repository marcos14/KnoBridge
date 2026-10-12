import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { Assistant } from "@/lib/api/assistants";
import type { Role } from "@/lib/api/auth";
import { formatDateTime } from "@/lib/intl";
import {
  ASSISTANT_ID,
  makeAssistant,
  makeAssistants,
  makeMe,
  makeWorkspace,
  WORKSPACE_ID,
} from "@/test/factories";
import {
  apiErrorResponse,
  assistantStore,
  makeWebhookTest,
  meAs,
  rotateWebhookSecretFails,
  updateAssistantFails,
  WEBHOOK_SECRET,
  WEBHOOK_SECRET_CREATED_AT,
} from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

const PATH = `/w/${WORKSPACE_ID}/assistants`;
const URL_LABEL = "URL do webhook";
const ENABLED = 'Oferecer "Abrir chamado" no chat';
const HOOK = "https://chamados.example.test/kb";

type Store = ReturnType<typeof assistantStore>;

/** Suporte ERP with `overrides` (the webhook fields), beside the default Rascunho. */
function assistantsWith(overrides: Partial<Assistant>): Assistant[] {
  return makeAssistants().map((item) =>
    item.id === ASSISTANT_ID ? makeAssistant({ ...item, ...overrides }) : item,
  );
}

const CONFIGURED = {
  ticket_webhook_url: HOOK,
  ticket_webhook_configured: true,
  ticket_webhook_secret_created_at: "2026-10-11T10:00:00Z",
};

function setup(
  role: Role = "owner",
  assistants: Assistant[] = makeAssistants(),
  options?: Parameters<typeof assistantStore>[1],
): Store {
  server.use(meAs(makeMe({ workspaces: [makeWorkspace({ role })] })));
  const store = assistantStore(assistants, options);
  server.use(...store.handlers);
  return store;
}

async function openEdit() {
  const user = userEvent.setup();
  renderWithProviders({ path: PATH });
  await user.click(await screen.findByRole("button", { name: "Editar Suporte ERP" }));
  const dialog = await screen.findByRole("dialog", { name: "Editar assistente" });
  return { user, dialog };
}

function panel(dialog: HTMLElement) {
  return within(dialog).getByRole("region", { name: "Segredo e teste do webhook" });
}

describe("assistant ticket webhook", () => {
  it("test_webhook_turned_on_saves_the_url_and_waits_for_a_secret", async () => {
    const store = setup();
    const { user, dialog } = await openEdit();
    expect(within(dialog).queryByLabelText(URL_LABEL)).not.toBeInTheDocument();
    expect(within(panel(dialog)).getByRole("button", { name: "Testar entrega" })).toBeDisabled();
    expect(
      within(panel(dialog)).getByText("Salve a URL e gere o segredo para testar."),
    ).toBeVisible();

    await user.click(within(dialog).getByRole("checkbox", { name: ENABLED }));
    await user.type(within(dialog).getByLabelText(URL_LABEL), HOOK);
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await screen.findByText("Assistente Suporte ERP atualizado.")).toBeVisible();
    expect(store.changes[0]?.body).toHaveProperty("ticket_webhook_url", HOOK);
    const reopened = await openEditAgain(user);
    expect(within(reopened).getByLabelText(URL_LABEL)).toHaveValue(HOOK);
    expect(
      within(panel(reopened)).getByText(
        "Nenhum segredo gerado ainda: sem ele, o chat não oferece abrir chamado.",
      ),
    ).toBeVisible();
  });

  it("test_webhook_requires_a_url_when_on", async () => {
    const store = setup();
    const { user, dialog } = await openEdit();

    await user.click(within(dialog).getByRole("checkbox", { name: ENABLED }));
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await within(dialog).findByText("Informe a URL do webhook.")).toBeVisible();
    await user.type(within(dialog).getByLabelText(URL_LABEL), "chamados.example.test");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));
    expect(
      await within(dialog).findByText("Informe uma URL http ou https válida, sem usuário e senha."),
    ).toBeVisible();
    expect(store.changes).toEqual([]);
  });

  it("test_webhook_turned_off_sends_null", async () => {
    const store = setup("owner", assistantsWith(CONFIGURED));
    const { user, dialog } = await openEdit();

    await user.click(within(dialog).getByRole("checkbox", { name: ENABLED }));
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    await screen.findByText("Assistente Suporte ERP atualizado.");
    expect(store.changes[0]?.body).toHaveProperty("ticket_webhook_url", null);
  });

  it("test_webhook_save_error_says_why_the_destination_was_refused", async () => {
    setup();
    server.use(updateAssistantFails(422, "webhook_destination_blocked", { reason: "loopback" }));
    const { user, dialog } = await openEdit();

    await user.click(within(dialog).getByRole("checkbox", { name: ENABLED }));
    await user.type(within(dialog).getByLabelText(URL_LABEL), "https://localhost/hook");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "O destino do webhook não é permitido. Motivo: o host aponta para o próprio servidor.",
    );
  });

  it("test_webhook_secret_is_generated_and_shown_once", async () => {
    const store = setup("admin", assistantsWith({ ticket_webhook_url: HOOK }));
    const { user, dialog } = await openEdit();

    await user.click(within(panel(dialog)).getByRole("button", { name: "Gerar segredo" }));

    expect(await within(dialog).findByLabelText("Segredo do webhook")).toHaveTextContent(
      WEBHOOK_SECRET,
    );
    expect(store.secretRotations).toEqual([ASSISTANT_ID]);
    await user.click(within(dialog).getByRole("button", { name: "Copiar segredo" }));
    await expect(navigator.clipboard.readText()).resolves.toBe(WEBHOOK_SECRET);
    await waitFor(() => {
      expect(
        within(panel(dialog)).getByText(
          `Segredo atual gerado em ${formatDateTime(new Date(WEBHOOK_SECRET_CREATED_AT), "pt-BR")}.`,
        ),
      ).toBeVisible();
    });
    expect(within(panel(dialog)).getByRole("button", { name: "Testar entrega" })).toBeEnabled();

    await user.click(within(dialog).getByRole("button", { name: "Cancelar" }));
    const reopened = await openEditAgain(user);
    expect(within(reopened).queryByText(WEBHOOK_SECRET)).not.toBeInTheDocument();
  });

  it("test_webhook_secret_replacement_asks_first", async () => {
    const store = setup("owner", assistantsWith(CONFIGURED));
    const { user, dialog } = await openEdit();

    await user.click(within(panel(dialog)).getByRole("button", { name: "Gerar novo segredo" }));
    expect(within(panel(dialog)).getByText(/O segredo atual deixa de valer/)).toBeVisible();
    await user.click(within(panel(dialog)).getByRole("button", { name: "Cancelar" }));
    expect(store.secretRotations).toEqual([]);

    await user.click(within(panel(dialog)).getByRole("button", { name: "Gerar novo segredo" }));
    await user.click(within(panel(dialog)).getByRole("button", { name: "Gerar e substituir" }));

    expect(await within(dialog).findByLabelText("Segredo do webhook")).toBeVisible();
    expect(store.secretRotations).toEqual([ASSISTANT_ID]);
  });

  it("test_webhook_secret_failure_is_shown", async () => {
    setup("owner", assistantsWith({ ticket_webhook_url: HOOK }));
    server.use(rotateWebhookSecretFails(403, "forbidden"));
    const { user, dialog } = await openEdit();

    await user.click(within(panel(dialog)).getByRole("button", { name: "Gerar segredo" }));

    expect(await within(panel(dialog)).findByRole("alert")).toHaveTextContent(
      "Você não tem permissão para fazer isso.",
    );
  });

  it("test_webhook_editor_tests_but_does_not_generate_the_secret", async () => {
    const store = setup("editor", assistantsWith(CONFIGURED));
    const { user, dialog } = await openEdit();

    expect(within(panel(dialog)).queryByRole("button", { name: /Gerar/ })).not.toBeInTheDocument();
    expect(
      within(panel(dialog)).getByText("Um owner ou admin do workspace gera o segredo."),
    ).toBeVisible();
    await user.click(within(panel(dialog)).getByRole("button", { name: "Testar entrega" }));

    const result = await within(panel(dialog)).findByRole("status");
    expect(result).toHaveTextContent("O destino aceitou a entrega de teste.");
    expect(result).toHaveTextContent(`Id da entrega: ${makeWebhookTest().delivery_id}`);
    expect(store.webhookTests).toEqual([ASSISTANT_ID]);
  });

  it("test_webhook_test_failure_shows_what_the_destination_answered", async () => {
    setup("owner", assistantsWith(CONFIGURED), {
      webhookTest: makeWebhookTest({
        ok: false,
        status: 500,
        error: { code: "webhook_rejected", message: "Rejected.", details: { status: 500 } },
      }),
    });
    const { user, dialog } = await openEdit();

    await user.click(within(panel(dialog)).getByRole("button", { name: "Testar entrega" }));

    expect(await within(panel(dialog)).findByRole("status")).toHaveTextContent(
      "A entrega de teste falhou. O destino recusou o envio. O destino respondeu HTTP 500.",
    );
  });

  it("test_webhook_test_refused_by_the_api_is_an_alert", async () => {
    setup("owner", assistantsWith(CONFIGURED), {
      webhookTest: apiErrorResponse(409, "ticket_webhook_not_configured"),
    });
    const { user, dialog } = await openEdit();

    await user.click(within(panel(dialog)).getByRole("button", { name: "Testar entrega" }));

    expect(await within(panel(dialog)).findByRole("alert")).toHaveTextContent(
      "O webhook de chamados deste assistente não está configurado.",
    );
  });
});

async function openEditAgain(user: ReturnType<typeof userEvent.setup>) {
  await waitFor(() => {
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
  await user.click(screen.getByRole("button", { name: "Editar Suporte ERP" }));
  return screen.findByRole("dialog", { name: "Editar assistente" });
}
