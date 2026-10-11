import { type APIRequestContext, type Browser, expect, type Page } from "@playwright/test";

import { emailedLink } from "./mailpit";

/**
 * Steps shared by the stack specs. The superadmin is fixed: on a fresh database the first spec
 * that needs it runs the setup, the others log in with the same credentials.
 */
export const ADMIN = {
  name: "Ana Admin",
  email: process.env.E2E_ADMIN_EMAIL ?? "admin@example.test",
  password: process.env.E2E_ADMIN_PASSWORD ?? "e2e-admin-password-1",
};

export const NO_SOURCE_ANSWER = "Não encontrei essa informação nas fontes que tenho disponíveis";
const INVITATION_SUBJECT = "Você foi convidado para um workspace no KnoBridge";

export interface Person {
  name: string;
  email: string;
  password: string;
}

/** A fresh browser context (own cookies and storage) for one person. */
export async function personPage(browser: Browser): Promise<Page> {
  const context = await browser.newContext();
  return context.newPage();
}

export async function login(page: Page, email: string, password: string): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("E-mail").fill(email);
  await page.getByLabel("Senha", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page).not.toHaveURL(/\/login/);
}

export async function logout(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Menu do usuário" }).click();
  await page.getByRole("menuitem", { name: "Sair" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Entrar" })).toBeVisible();
}

/** Runs the initial setup on a fresh database (then logs out), and logs the superadmin in. */
export async function adminLogin(page: Page, request: APIRequestContext): Promise<void> {
  const status = await request.get("/v1/setup/status");
  const { needs_setup: needsSetup } = (await status.json()) as { needs_setup: boolean };
  if (needsSetup) {
    await page.goto("/setup");
    await page.getByLabel("Nome").fill(ADMIN.name);
    await page.getByLabel("E-mail").fill(ADMIN.email);
    await page.getByLabel("Senha", { exact: true }).fill(ADMIN.password);
    await page.getByLabel("Confirme a senha").fill(ADMIN.password);
    await page.getByRole("button", { name: "Criar conta e entrar" }).click();
    await expect(page.getByRole("button", { name: "Menu do usuário" })).toBeVisible();
    await logout(page);
  }
  await login(page, ADMIN.email, ADMIN.password);
}

/** The superadmin creates a workspace and invites its owner by e-mail. */
export async function createWorkspace(
  admin: Page,
  workspace: string,
  ownerEmail: string,
): Promise<void> {
  await admin.goto("/admin/workspaces");
  await admin.getByRole("button", { name: "Criar workspace" }).click();
  const dialog = admin.getByRole("dialog", { name: "Criar workspace" });
  await dialog.getByLabel("Nome").fill(workspace);
  await dialog.getByLabel("E-mail do proprietário").fill(ownerEmail);
  await dialog.getByRole("button", { name: "Criar" }).click();
  await expect(
    admin.getByText(
      `Workspace ${workspace} criado. Enviamos o convite de proprietário para ${ownerEmail}.`,
    ),
  ).toBeVisible();
}

/** Opens the e-mailed invitation, creates the account and returns the workspace id. */
export async function acceptInvitation(page: Page, person: Person): Promise<string> {
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

export async function pickOption(page: Page, combobox: string, option: string): Promise<void> {
  await page.getByRole("combobox", { name: combobox }).click();
  await page.getByRole("option", { name: option }).click();
}

/** Registers the `fake` LLM provider (no network), which also embeds. */
export async function createFakeProvider(
  page: Page,
  workspaceId: string,
  name: string,
): Promise<void> {
  await page.goto(`/w/${workspaceId}/providers`);
  await page.getByRole("button", { name: "Novo provedor" }).click();
  const dialog = page.getByRole("dialog", { name: "Novo provedor" });
  await pickOption(page, "Tipo", "Fake (testes, sem rede)");
  await dialog.getByLabel("Nome").fill(name);
  await dialog.getByLabel("Chave de API").fill("fake-e2e-key");
  await dialog.getByRole("button", { name: "Salvar" }).click();
  await expect(page.getByText(`Provedor ${name} cadastrado.`)).toBeVisible();
}

/** A collection embedded by the only credential (preselected), with the suggested model. */
export async function createCollection(
  page: Page,
  workspaceId: string,
  name: string,
  provider: string,
): Promise<void> {
  await page.goto(`/w/${workspaceId}/collections`);
  await page.getByRole("button", { name: "Nova coleção" }).click();
  const dialog = page.getByRole("dialog", { name: "Nova coleção" });
  await dialog.getByLabel("Nome").fill(name);
  await expect(dialog.getByRole("combobox", { name: "Credencial de embedding" })).toHaveText(
    provider,
  );
  await dialog.getByRole("button", { name: "Salvar" }).click();
  await expect(page.getByText(`Coleção ${name} criada.`)).toBeVisible();
}

/** Starts a new conversation with the only assistant and sends `question`. */
export async function ask(
  page: Page,
  workspaceId: string,
  assistant: string,
  question: string,
): Promise<void> {
  await page.goto(`/w/${workspaceId}/chat`);
  await expect(page.getByRole("combobox", { name: "Assistente" })).toHaveText(assistant);
  const box = page.getByRole("textbox", { name: "Sua pergunta" });
  await box.fill(question);
  await box.press("Enter");
  await expect(page).toHaveURL(/\/chat\/[0-9a-f-]{36}$/);
}
