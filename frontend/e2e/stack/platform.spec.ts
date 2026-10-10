import { type Browser, expect, type Page, test } from "@playwright/test";

import { emailedLink } from "./mailpit";

// The navigable platform end to end, against the real stack (API, Postgres, Mailpit, nginx): the
// first superadmin sets the instance up, creates a workspace for an owner, who joins by the
// e-mailed invitation and invites a viewer; the viewer recovers the password, chats with an
// assistant on the `fake` provider (no source, so the "no source" answer) and rates it; the owner
// finds the conversation; the chosen theme follows the account.
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

test("test_platform_flows_from_setup_to_conversation_review", async ({ browser, request }) => {
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
    await viewer.goto(`/w/${workspaceId}/chat`);
    await expect(viewer.getByRole("combobox", { name: "Assistente" })).toHaveText(ASSISTANT);
    const question = viewer.getByRole("textbox", { name: "Sua pergunta" });
    await question.fill(QUESTION);
    await question.press("Enter");

    await expect(viewer).toHaveURL(/\/chat\/[0-9a-f-]{36}$/);
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
});
