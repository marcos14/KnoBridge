import { type Browser, expect, type Page, test } from "@playwright/test";

import { emailedLink } from "./mailpit";

// The navigable platform end to end, against the real stack (API, Postgres, Mailpit, nginx): the
// first superadmin sets the instance up, creates a workspace for an owner, who joins by the
// e-mailed invitation and invites a viewer; the viewer recovers the password, chats with an
// assistant on the `fake` provider (no source, so the "no source" answer) and rates it; the owner
// finds the conversation; the chosen theme follows the account. Then the owner indexes the
// synthetic folder mounted at /sources (collection, folder source, connection test, sync, search),
// links the collection to the assistant and gets an answer citing the file, while an unrelated
// question still gets the "no source" answer.
//
// Every address is synthetic (@example.test). The superadmin is fixed: on a fresh database the
// test runs the setup, on a used one it logs in with the same credentials. Everyone else gets a
// per-run suffix, so a rerun never collides with what an earlier run left behind.
const ADMIN = {
  name: "Ana Admin",
  email: process.env.E2E_ADMIN_EMAIL ?? "admin@example.test",
  password: process.env.E2E_ADMIN_PASSWORD ?? "e2e-admin-password-1",
};
const RUN = Date.now().toString(36);
const OWNER = {
  name: "Olga Owner",
  email: `owner-${RUN}@example.test`,
  password: "e2e-owner-password-1",
};
const VIEWER = {
  name: `Vitor Viewer ${RUN}`,
  email: `viewer-${RUN}@example.test`,
  password: "e2e-viewer-password-1",
  newPassword: "e2e-viewer-password-2",
};
const WORKSPACE = `Acme E2E ${RUN}`;
const PROVIDER = "Fake E2E";
const ASSISTANT = "Suporte E2E";
const QUESTION = `Como emito a nota de devolução ${RUN}?`;
const NO_SOURCE_ANSWER = "Não encontrei essa informação nas fontes que tenho disponíveis";

// Knowledge: deploy/docker-compose.e2e.yml mounts e2e/stack/fixtures/ at /sources, so the
// synthetic folder knowledge/ (two Markdown files and one TypeScript file) is /sources/knowledge.
const COLLECTION = `Base E2E ${RUN}`;
const SOURCE = `Manual E2E ${RUN}`;
const SOURCE_PATH = "/sources/knowledge";
const KNOWN_FILE = "fechamento-de-caixa.md";
const SEARCH_TERM = "sangria";
// Every term is in one section of KNOWN_FILE, so the full-text arm finds it. No run suffix here:
// it would be a term the section lacks.
const KNOWLEDGE_QUESTION = "Como registrar a sangria do caixa?";
// No word in common with the fixtures: neither search arm finds anything (rule 8).
const UNRELATED_QUESTION = `Previsão meteorológica para Júpiter ${RUN}`;
// Indexing runs in the worker (Temporal): generous, but bounded.
const SYNC_TIMEOUT = 120_000;

const INVITATION_SUBJECT = "Você foi convidado para um workspace no KnoBridge";
const RESET_SUBJECT = "Redefinição de senha do KnoBridge";

/** A fresh browser context (own cookies and storage) for one person. */
async function personPage(browser: Browser): Promise<Page> {
  const context = await browser.newContext();
  return context.newPage();
}

async function login(page: Page, email: string, password: string): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("E-mail").fill(email);
  await page.getByLabel("Senha", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page).not.toHaveURL(/\/login/);
}

async function logout(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Menu do usuário" }).click();
  await page.getByRole("menuitem", { name: "Sair" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Entrar" })).toBeVisible();
}

/** Opens the e-mailed invitation, creates the account and returns the workspace id. */
async function acceptInvitation(
  page: Page,
  person: { name: string; email: string; password: string },
): Promise<string> {
  const link = await emailedLink(
    page.request,
    person.email,
    INVITATION_SUBJECT,
    "/accept-invitation",
  );
  await page.goto(link);
  await expect(page.getByText(`Convite enviado para ${person.email}.`)).toBeVisible();
  await page.getByLabel("Nome").fill(person.name);
  await page.getByLabel("Senha", { exact: true }).fill(person.password);
  await page.getByLabel("Confirme a senha").fill(person.password);
  await page.getByRole("button", { name: "Criar conta e aceitar" }).click();
  await expect(page).toHaveURL(/\/w\/[0-9a-f-]{36}/);
  return String(/\/w\/([0-9a-f-]{36})/.exec(page.url())?.[1]);
}

async function pickOption(page: Page, combobox: string, option: string): Promise<void> {
  await page.getByRole("combobox", { name: combobox }).click();
  await page.getByRole("option", { name: option }).click();
}

/** Starts a new conversation with the only assistant and sends `question`. */
async function ask(page: Page, workspaceId: string, question: string): Promise<void> {
  await page.goto(`/w/${workspaceId}/chat`);
  await expect(page.getByRole("combobox", { name: "Assistente" })).toHaveText(ASSISTANT);
  const box = page.getByRole("textbox", { name: "Sua pergunta" });
  await box.fill(question);
  await box.press("Enter");
  await expect(page).toHaveURL(/\/chat\/[0-9a-f-]{36}$/);
}

test("test_platform_flows_from_setup_to_conversation_review", async ({ browser, request }) => {
  // Setup, invitations and a whole indexing run in one flow: above the config's 180 s.
  test.setTimeout(360_000);
  const admin = await personPage(browser);
  const owner = await personPage(browser);
  const viewer = await personPage(browser);
  let workspaceId = "";

  await test.step("setup creates the first superadmin, who logs out and back in", async () => {
    const status = await request.get("/v1/setup/status");
    const { needs_setup: needsSetup } = (await status.json()) as { needs_setup: boolean };
    if (needsSetup) {
      await admin.goto("/setup");
      await admin.getByLabel("Nome").fill(ADMIN.name);
      await admin.getByLabel("E-mail").fill(ADMIN.email);
      await admin.getByLabel("Senha", { exact: true }).fill(ADMIN.password);
      await admin.getByLabel("Confirme a senha").fill(ADMIN.password);
      await admin.getByRole("button", { name: "Criar conta e entrar" }).click();
      await expect(admin.getByRole("button", { name: "Menu do usuário" })).toBeVisible();
      await logout(admin);
    }
    await login(admin, ADMIN.email, ADMIN.password);
  });

  await test.step("superadmin creates a workspace and invites its owner", async () => {
    await admin.goto("/admin/workspaces");
    await admin.getByRole("button", { name: "Criar workspace" }).click();
    const dialog = admin.getByRole("dialog", { name: "Criar workspace" });
    await dialog.getByLabel("Nome").fill(WORKSPACE);
    await dialog.getByLabel("E-mail do proprietário").fill(OWNER.email);
    await dialog.getByRole("button", { name: "Criar" }).click();
    await expect(
      admin.getByText(
        `Workspace ${WORKSPACE} criado. Enviamos o convite de proprietário para ${OWNER.email}.`,
      ),
    ).toBeVisible();
  });

  await test.step("owner accepts the invitation from the e-mail", async () => {
    workspaceId = await acceptInvitation(owner, OWNER);
  });

  await test.step("owner invites a viewer, who accepts", async () => {
    await owner.goto(`/w/${workspaceId}/members`);
    await owner.getByRole("button", { name: "Convidar" }).click();
    const dialog = owner.getByRole("dialog", { name: "Convidar para o workspace" });
    await dialog.getByLabel("E-mail").fill(VIEWER.email);
    await pickOption(owner, "Papel", "Leitor");
    await dialog.getByRole("button", { name: "Enviar convite" }).click();
    await expect(owner.getByText(`Convite enviado para ${VIEWER.email}.`)).toBeVisible();

    expect(await acceptInvitation(viewer, VIEWER)).toBe(workspaceId);
  });

  await test.step("viewer forgets the password and sets a new one", async () => {
    await logout(viewer);
    await viewer.getByRole("link", { name: "Esqueci minha senha" }).click();
    // The login form also has an "E-mail" field: wait for the new page before filling.
    await expect(viewer.getByRole("heading", { level: 1, name: "Recuperar senha" })).toBeVisible();
    await viewer.getByLabel("E-mail").fill(VIEWER.email);
    await viewer.getByRole("button", { name: "Enviar link" }).click();
    await expect(viewer.getByText(/Se houver uma conta com esse e-mail/)).toBeVisible();

    const link = await emailedLink(viewer.request, VIEWER.email, RESET_SUBJECT, "/reset-password");
    await viewer.goto(link);
    await viewer.getByLabel("Nova senha").fill(VIEWER.newPassword);
    await viewer.getByLabel("Confirme a senha").fill(VIEWER.newPassword);
    await viewer.getByRole("button", { name: "Salvar nova senha" }).click();
    await expect(viewer.getByText("Senha alterada. Entre com a nova senha.")).toBeVisible();

    await login(viewer, VIEWER.email, VIEWER.newPassword);
  });

  await test.step("owner registers the fake provider and an assistant", async () => {
    await owner.goto(`/w/${workspaceId}/providers`);
    await owner.getByRole("button", { name: "Novo provedor" }).click();
    const providerDialog = owner.getByRole("dialog", { name: "Novo provedor" });
    await pickOption(owner, "Tipo", "Fake (testes, sem rede)");
    await providerDialog.getByLabel("Nome").fill(PROVIDER);
    await providerDialog.getByLabel("Chave de API").fill("fake-e2e-key");
    await providerDialog.getByRole("button", { name: "Salvar" }).click();
    await expect(owner.getByText(`Provedor ${PROVIDER} cadastrado.`)).toBeVisible();

    await owner.goto(`/w/${workspaceId}/assistants`);
    await owner.getByRole("button", { name: "Novo assistente" }).click();
    const assistantDialog = owner.getByRole("dialog", { name: "Novo assistente" });
    await assistantDialog.getByLabel("Nome").fill(ASSISTANT);
    await pickOption(owner, "Provedor", PROVIDER);
    await assistantDialog.getByLabel("Modelo").fill("fake-chat");
    await assistantDialog.getByRole("button", { name: "Salvar" }).click();
    await expect(owner.getByText(`Assistente ${ASSISTANT} criado.`)).toBeVisible();
  });

  await test.step("viewer asks, gets the no-source answer and rates it", async () => {
    await ask(viewer, workspaceId, QUESTION);

    await expect(viewer.getByText(NO_SOURCE_ANSWER)).toBeVisible();
    // Rule 8: without a source the assistant says so and offers a ticket.
    await expect(viewer.getByRole("button", { name: "Abrir chamado" })).toBeDisabled();
    await viewer.getByRole("button", { name: "Resposta não ajudou" }).click();
    await expect(viewer.getByText("Obrigado pela avaliação.")).toBeVisible();
    await expect(viewer.getByRole("button", { name: "Resposta não ajudou" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  await test.step("owner finds the rated conversation", async () => {
    await owner.goto(`/w/${workspaceId}/conversations`);
    const table = owner.getByRole("table", { name: "Conversas do workspace" });
    const row = table.getByRole("row").filter({ hasText: QUESTION });
    await expect(row.getByLabel("0 positivas, 1 negativas")).toBeVisible();
    await row.getByRole("link", { name: QUESTION }).click();

    await expect(owner.getByText(NO_SOURCE_ANSWER)).toBeVisible();
    await expect(
      owner.getByText("Respondida sem fonte: o assistente ofereceu abrir chamado."),
    ).toBeVisible();
    await expect(owner.getByText(`👎 ${VIEWER.name}`)).toBeVisible();
  });

  await test.step("the chosen theme follows the account to a new browser", async () => {
    await viewer.getByRole("button", { name: "Menu do usuário" }).click();
    const saved = viewer.waitForResponse(
      (response) => response.request().method() === "PATCH" && response.url().endsWith("/v1/me"),
    );
    await viewer.getByRole("menuitemradio", { name: "Escuro" }).click();
    await expect(viewer.locator("html")).toHaveClass("dark");
    expect((await saved).ok()).toBe(true);
    await viewer.reload();
    await expect(viewer.locator("html")).toHaveClass("dark");

    // A new context has no localStorage: the dark theme can only come from the profile.
    const elsewhere = await personPage(browser);
    await login(elsewhere, VIEWER.email, VIEWER.newPassword);
    await expect(elsewhere.locator("html")).toHaveClass("dark");
  });

  await test.step("owner creates a collection embedded by the fake provider", async () => {
    await owner.goto(`/w/${workspaceId}/collections`);
    await owner.getByRole("button", { name: "Nova coleção" }).click();
    const dialog = owner.getByRole("dialog", { name: "Nova coleção" });
    await dialog.getByLabel("Nome").fill(COLLECTION);
    // The only embedding credential comes preselected; the fake accepts the suggested model.
    await expect(dialog.getByRole("combobox", { name: "Credencial de embedding" })).toHaveText(
      PROVIDER,
    );
    await dialog.getByRole("button", { name: "Salvar" }).click();
    await expect(owner.getByText(`Coleção ${COLLECTION} criada.`)).toBeVisible();
  });

  await test.step("owner adds the mounted folder as a source and tests it", async () => {
    await owner.goto(`/w/${workspaceId}/sources`);
    await owner.getByRole("button", { name: "Nova fonte" }).click();
    const dialog = owner.getByRole("dialog", { name: "Nova fonte" });
    await dialog.getByLabel("Nome").fill(SOURCE);
    await expect(dialog.getByRole("combobox", { name: "Coleção" })).toHaveText(COLLECTION);
    await dialog.getByRole("radio", { name: "Pasta" }).click();
    await dialog.getByLabel("Caminho da pasta").fill(SOURCE_PATH);
    await dialog.getByRole("button", { name: "Salvar" }).click();
    await expect(owner.getByText(`Fonte ${SOURCE} criada.`)).toBeVisible();

    await owner.getByRole("link", { name: SOURCE }).click();
    await expect(owner.getByRole("heading", { level: 1, name: SOURCE })).toBeVisible();
    await owner.getByRole("button", { name: "Testar conexão" }).click();
    await expect(owner.getByText(`A fonte ${SOURCE} está acessível.`)).toBeVisible();
  });

  await test.step("owner syncs the source and sees the run succeed", async () => {
    await owner.getByRole("button", { name: `Sincronizar ${SOURCE} agora` }).click();
    await expect(owner.getByText(`Sincronização de ${SOURCE} na fila.`)).toBeVisible();

    // The screen polls while the run is active; wait for a final status, then require success.
    const runs = owner.getByRole("table", { name: "Execuções da fonte" });
    const status = runs.getByRole("row").nth(1).getByRole("cell").first();
    await expect(status).toHaveText(/Concluída|Falhou|Cancelada/, { timeout: SYNC_TIMEOUT });
    await expect(status).toHaveText("Concluída");
    await expect(owner.getByText("Documentos indexados: 3")).toBeVisible();
  });

  await test.step("owner tests the search with a word of the fixture", async () => {
    await owner.goto(`/w/${workspaceId}/collections`);
    await owner.getByRole("link", { name: COLLECTION }).click();
    await expect(owner.getByRole("heading", { level: 1, name: COLLECTION })).toBeVisible();
    await owner.getByLabel("Pergunta ou termos").fill(SEARCH_TERM);
    await owner.getByRole("button", { name: "Buscar" }).click();

    const results = owner.getByRole("list", { name: "Resultados da busca" });
    await expect(results.getByText(KNOWN_FILE, { exact: false }).first()).toBeVisible();
  });

  await test.step("owner links the collection to the assistant", async () => {
    await owner.goto(`/w/${workspaceId}/assistants`);
    await owner.getByRole("button", { name: `Editar ${ASSISTANT}` }).click();
    const dialog = owner.getByRole("dialog", { name: "Editar assistente" });
    await dialog.getByRole("checkbox", { name: COLLECTION }).check();
    await dialog.getByRole("button", { name: "Salvar" }).click();
    await expect(owner.getByText(`Assistente ${ASSISTANT} atualizado.`)).toBeVisible();
  });

  await test.step("owner asks about the fixture and opens the cited file", async () => {
    await ask(owner, workspaceId, KNOWLEDGE_QUESTION);

    // The list of sources: "[n] <path>" followed by the short location.
    const cited = owner.getByRole("button", {
      name: new RegExp(`^\\[\\d+\\] ${KNOWN_FILE.replaceAll(".", "\\.")}`),
    });
    await expect(cited.first()).toBeVisible();
    await expect(owner.getByText(NO_SOURCE_ANSWER)).toHaveCount(0);
    await cited.first().click();
    const panel = owner.getByRole("dialog", {
      name: new RegExp(KNOWN_FILE.replaceAll(".", "\\.")),
    });
    await expect(panel.getByText("Arquivo", { exact: true })).toBeVisible();
    await expect(panel.getByText(KNOWN_FILE, { exact: true })).toBeVisible();
    await expect(panel.getByText(/sangria/).first()).toBeVisible();
    await panel.getByRole("button", { name: "Fechar" }).click();
  });

  await test.step("an unrelated question still gets the no-source answer", async () => {
    await ask(owner, workspaceId, UNRELATED_QUESTION);

    await expect(owner.getByText(NO_SOURCE_ANSWER)).toBeVisible();
    await expect(owner.getByRole("button", { name: "Abrir chamado" })).toBeDisabled();
  });
});
