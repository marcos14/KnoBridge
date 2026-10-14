import {
  type APIRequestContext,
  type Browser,
  expect,
  type Locator,
  type Page,
} from "@playwright/test";

import { emailedLink } from "./mailpit";
import { setSinkSecret, SINK_HOOK_URL } from "./webhookSink";

/**
 * Steps shared by the stack specs. The superadmin is fixed: on a fresh database the first spec
 * that needs it runs the setup, the others log in with the same credentials.
 */
export const ADMIN = {
  name: "Ana Admin",
  email: process.env.E2E_ADMIN_EMAIL ?? "admin@example.test",
  password: process.env.E2E_ADMIN_PASSWORD ?? "e2e-admin-password-1",
  // The first workspace, created by the setup with the superadmin as owner.
  workspace: "Workspace da administração",
};

/**
 * The synthetic knowledge: docker-compose.e2e.yml mounts e2e/stack/fixtures/ at /sources, so the
 * folder knowledge/ (two Markdown files and one TypeScript file) is /sources/knowledge. Every
 * term of `question` is in one section of `file`, so the full-text arm finds it (no run suffix
 * there: it would be a term the section lacks).
 */
export const KNOWLEDGE = {
  path: "/sources/knowledge",
  documents: 3,
  file: "fechamento-de-caixa.md",
  question: "Como registrar a sangria do caixa?",
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

export async function needsSetup(request: APIRequestContext): Promise<boolean> {
  const status = await request.get("/v1/setup/status");
  return ((await status.json()) as { needs_setup: boolean }).needs_setup;
}

const WORKSPACE_URL = /\/w\/([0-9a-f-]{36})$/;

/** The workspace id in the current URL (`/w/<id>`), once the page is there. */
async function workspaceIdFromUrl(page: Page): Promise<string> {
  await expect(page).toHaveURL(WORKSPACE_URL);
  return String(WORKSPACE_URL.exec(new URL(page.url()).pathname)?.[1]);
}

/**
 * The initial setup on a fresh database: the panel sends the visitor to `/setup`, which creates
 * the superadmin and the first workspace (no invitation) and lands on its home. Returns its id.
 */
export async function setupInstance(page: Page): Promise<string> {
  await page.goto("/");
  await expect(page).toHaveURL(/\/setup/);
  await page.getByLabel("Nome", { exact: true }).fill(ADMIN.name);
  await page.getByLabel("E-mail").fill(ADMIN.email);
  await page.getByLabel("Senha", { exact: true }).fill(ADMIN.password);
  await page.getByLabel("Confirme a senha").fill(ADMIN.password);
  await page.getByLabel("Nome do workspace").fill(ADMIN.workspace);
  await page.getByRole("button", { name: "Criar conta e entrar" }).click();
  return workspaceIdFromUrl(page);
}

/** Runs the initial setup on a fresh database (then logs out), and logs the superadmin in. */
export async function adminLogin(page: Page, request: APIRequestContext): Promise<void> {
  if (await needsSetup(request)) {
    await setupInstance(page);
    await expect(page.getByRole("button", { name: "Menu do usuário" })).toBeVisible();
    await logout(page);
  }
  await login(page, ADMIN.email, ADMIN.password);
}

/** Id of a workspace the logged-in person sees, by name (from `GET /v1/me`). */
export async function workspaceIdByName(page: Page, name: string): Promise<string> {
  const response = await page.request.get("/v1/me");
  expect(response.ok()).toBe(true);
  const { workspaces } = (await response.json()) as {
    workspaces: { id: string; name: string }[];
  };
  const workspace = workspaces.find((item) => item.name === name);
  expect(workspace, `workspace ${name} in /v1/me`).toBeDefined();
  return String(workspace?.id);
}

/**
 * The superadmin enters a workspace from the instance administration (effective admin role, no
 * membership) and lands on its home, under the superadmin banner. Returns the workspace id.
 */
export async function enterWorkspace(admin: Page, workspace: string): Promise<string> {
  await admin.goto("/admin/workspaces");
  await admin.getByRole("searchbox", { name: "Buscar" }).fill(workspace);
  await admin.getByRole("button", { name: "Buscar", exact: true }).click();
  await admin.getByRole("button", { name: `Entrar em ${workspace}` }).click();
  const workspaceId = await workspaceIdFromUrl(admin);
  await expect(admin.getByText(`Acesso de superadmin a ${workspace}`)).toBeVisible();
  return workspaceId;
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

/** The three response levels, by their name on the panel (`docs/specs/produtos-e-niveis.md`). */
export const LEVELS = {
  end_user: "Usuário final",
  support: "Suporte",
  product_dev: "Desenvolvimento e produto",
} as const;

export type Level = keyof typeof LEVELS;

/**
 * Configures every response level of the workspace (Configurações > Níveis de resposta) with
 * `provider` and the fake chat model: without it, no product answers (409 level_not_configured).
 */
export async function configureLevels(
  page: Page,
  workspaceId: string,
  provider: string,
): Promise<void> {
  await page.goto(`/w/${workspaceId}/settings`);
  await expect(
    page.getByRole("heading", { level: 1, name: "Configurações do workspace" }),
  ).toBeVisible();
  for (const name of Object.values(LEVELS)) {
    const form = page.getByRole("form", { name, exact: true });
    await form.getByRole("combobox", { name: "Credencial" }).click();
    await page.getByRole("option", { name: provider }).click();
    await form.getByLabel("Modelo").fill("fake-chat");
    await form.getByRole("button", { name: "Salvar nível" }).click();
    await expect(form.getByText(`Nível ${name} atualizado.`)).toBeVisible();
  }
}

/** A product answering from `collections` (the model comes from the workspace's levels). */
export async function createProduct(
  page: Page,
  workspaceId: string,
  name: string,
  collections: readonly string[] = [],
): Promise<void> {
  await page.goto(`/w/${workspaceId}/products`);
  await page.getByRole("button", { name: "Novo produto" }).click();
  const dialog = page.getByRole("dialog", { name: "Novo produto" });
  await dialog.getByLabel("Nome", { exact: true }).fill(name);
  for (const collection of collections) {
    await dialog.getByRole("checkbox", { name: collection }).check();
  }
  await dialog.getByRole("button", { name: "Salvar" }).click();
  await expect(page.getByText(`Produto ${name} criado.`)).toBeVisible();
}

/** Opens the edit dialog of `product` on the products screen. */
export async function editProduct(
  page: Page,
  workspaceId: string,
  product: string,
): Promise<Locator> {
  await page.goto(`/w/${workspaceId}/products`);
  await page.getByRole("button", { name: `Editar ${product}` }).click();
  return page.getByRole("dialog", { name: "Editar produto" });
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

/**
 * A folder source of `collection` at `path` (inside the containers, under /sources), left on its
 * detail page after a successful connection test.
 */
export async function createFolderSource(
  page: Page,
  workspaceId: string,
  name: string,
  collection: string,
  path: string,
  minLevel?: Level,
): Promise<void> {
  await page.goto(`/w/${workspaceId}/sources`);
  await page.getByRole("button", { name: "Nova fonte" }).click();
  const dialog = page.getByRole("dialog", { name: "Nova fonte" });
  await dialog.getByLabel("Nome").fill(name);
  await expect(dialog.getByRole("combobox", { name: "Coleção" })).toHaveText(collection);
  await dialog.getByRole("radio", { name: "Pasta" }).click();
  await dialog.getByLabel("Caminho da pasta").fill(path);
  // A folder defaults to the end user level; only owners and admins pick another one.
  const level = dialog.getByRole("combobox", { name: "Nível mínimo" });
  await expect(level).toHaveText(`${LEVELS.end_user} (padrão)`);
  if (minLevel !== undefined) {
    await level.click();
    await page.getByRole("option", { name: LEVELS[minLevel], exact: true }).click();
    await expect(level).toHaveText(LEVELS[minLevel]);
  }
  await dialog.getByRole("button", { name: "Salvar" }).click();
  await expect(page.getByText(`Fonte ${name} criada.`)).toBeVisible();

  await page.getByRole("link", { name }).click();
  await expect(page.getByRole("heading", { level: 1, name })).toBeVisible();
  await page.getByRole("button", { name: "Testar conexão" }).click();
  await expect(page.getByText(`A fonte ${name} está acessível.`)).toBeVisible();
}

/**
 * On the detail page of a tickets or cards source: generates its send token (`kbi_…`), shown
 * once, and returns it.
 */
export async function issueIngestToken(page: Page, source: string): Promise<string> {
  await page.getByRole("button", { name: "Gerar token" }).click();
  const confirm = page.getByRole("dialog", { name: `Gerar o token de envio de ${source}?` });
  await confirm.getByRole("button", { name: "Gerar" }).click();
  const issued = page.getByRole("dialog", { name: "Token de envio gerado" });
  const shown = issued.getByText(/^kbi_[a-z0-9]{8}_[A-Za-z0-9_-]{43}$/);
  await expect(shown).toBeVisible();
  const token = (await shown.textContent()) ?? "";
  await issued.getByRole("button", { name: "Concluir" }).click();
  await expect(page.getByText(/^Token atual: kbi_[a-z0-9]{8}_…/)).toBeVisible();
  return token;
}

/** Indexing runs in the worker (Temporal): generous, but bounded. */
const SYNC_TIMEOUT = 120_000;

/** On the source's detail page: syncs it and requires a successful run with `documents`. */
export async function syncSource(page: Page, name: string, documents: number): Promise<void> {
  await page.getByRole("button", { name: `Sincronizar ${name} agora` }).click();
  await expect(page.getByText(`Sincronização de ${name} na fila.`)).toBeVisible();

  // The screen polls while the run is active; wait for a final status, then require success.
  const runs = page.getByRole("table", { name: "Execuções da fonte" });
  const status = runs.getByRole("row").nth(1).getByRole("cell").first();
  await expect(status).toHaveText(/Concluída|Falhou|Cancelada/, { timeout: SYNC_TIMEOUT });
  await expect(status).toHaveText("Concluída");
  await expect(page.getByText(`Documentos indexados: ${String(documents)}`)).toBeVisible();
}

/**
 * Starts a new conversation with `product` (the only one of the workspace) at `level` (default:
 * the person's maximum in the product, preselected) and sends `question`. Once it starts, the
 * conversation shows its level.
 */
export async function ask(
  page: Page,
  workspaceId: string,
  product: string,
  question: string,
  level?: Level,
): Promise<void> {
  await page.goto(`/w/${workspaceId}/chat`);
  await expect(page.getByRole("combobox", { name: "Produto", exact: true })).toHaveText(product);
  if (level !== undefined) {
    const choice = page.getByRole("radio", { name: LEVELS[level], exact: true });
    await choice.click();
    await expect(choice).toBeChecked();
  }
  const box = page.getByRole("textbox", { name: "Sua pergunta" });
  await box.fill(question);
  await box.press("Enter");
  await expect(page).toHaveURL(/\/chat\/[0-9a-f-]{36}$/);
}

/**
 * Creates an API key on the panel (all products, `level` or the preselected end user level) and
 * returns the `kbk_…` the panel shows once.
 */
export async function createApiKey(
  page: Page,
  workspaceId: string,
  name: string,
  level?: Level,
): Promise<string> {
  await page.goto(`/w/${workspaceId}/api-keys`);
  await page.getByRole("button", { name: "Nova chave" }).click();
  const dialog = page.getByRole("dialog", { name: "Nova chave de API" });
  await dialog.getByLabel("Nome").fill(name);
  // The panel preselects the lowest level: the key's owner raises it on purpose.
  await expect(dialog.getByRole("radio", { name: LEVELS.end_user })).toBeChecked();
  if (level !== undefined) {
    await dialog.getByRole("radio", { name: LEVELS[level] }).click();
  }
  await dialog.getByRole("button", { name: "Salvar" }).click();

  const secret = page.getByRole("dialog", { name: `Chave ${name} criada` });
  const key = secret.getByText(/^kbk_[a-z0-9]{8}_/);
  await expect(key).toBeVisible();
  const apiKey = (await key.textContent())?.trim() ?? "";
  expect(apiKey).toMatch(/^kbk_[a-z0-9]{8}_[A-Za-z0-9_-]{43}$/);
  await secret.getByRole("button", { name: "Concluído" }).click();
  return apiKey;
}

/**
 * Points the "Abrir chamado" webhook of `product` at the fake ticket system of the compose,
 * generates the secret (shown once), hands it to the receiver and checks a test delivery.
 */
export async function connectTicketWebhook(
  page: Page,
  workspaceId: string,
  product: string,
): Promise<void> {
  const dialog = await editProduct(page, workspaceId, product);
  await dialog.getByRole("checkbox", { name: 'Oferecer "Abrir chamado" no chat' }).check();
  await dialog.getByLabel("URL do webhook").fill(SINK_HOOK_URL);
  await dialog.getByRole("button", { name: "Salvar" }).click();
  await expect(page.getByText(`Produto ${product} atualizado.`)).toBeVisible();

  await page.getByRole("button", { name: `Editar ${product}` }).click();
  const edit = page.getByRole("dialog", { name: "Editar produto" });
  const panel = edit.getByRole("region", { name: "Segredo e teste do webhook" });
  await panel.getByRole("button", { name: "Gerar segredo" }).click();
  const secret = edit.getByLabel("Segredo do webhook");
  await expect(secret).toHaveText(/^kbw_/);
  await setSinkSecret((await secret.textContent()) ?? "");
  await panel.getByRole("button", { name: "Testar entrega" }).click();
  await expect(panel.getByRole("status")).toContainText("O destino aceitou a entrega de teste.");
  await edit.getByRole("button", { name: "Cancelar" }).click();
  await expect(edit).toBeHidden();
}
