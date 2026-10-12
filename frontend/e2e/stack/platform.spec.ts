import { expect, type Page, test } from "@playwright/test";

import {
  acceptInvitation,
  adminLogin,
  ask as askAssistant,
  createCollection,
  createFakeProvider,
  createWorkspace,
  login,
  logout,
  NO_SOURCE_ANSWER,
  personPage,
  pickOption,
} from "./flows";
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

const RESET_SUBJECT = "Redefinição de senha do KnoBridge";

/** Starts a new conversation with the only assistant and sends `question`. */
async function ask(page: Page, workspaceId: string, question: string): Promise<void> {
  await askAssistant(page, workspaceId, ASSISTANT, question);
}

test("test_platform_flows_from_setup_to_conversation_review", async ({ browser, request }) => {
  // Setup, invitations and a whole indexing run in one flow: above the config's 180 s.
  test.setTimeout(360_000);
  const admin = await personPage(browser);
  const owner = await personPage(browser);
  const viewer = await personPage(browser);
  let workspaceId = "";

  await test.step("setup creates the first superadmin, who logs out and back in", async () => {
    await adminLogin(admin, request);
  });

  await test.step("superadmin creates a workspace and invites its owner", async () => {
    await createWorkspace(admin, WORKSPACE, OWNER.email);
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
    await createFakeProvider(owner, workspaceId, PROVIDER);

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
    // Rule 8: without a source the assistant says so. The "Abrir chamado" button only appears
    // when the assistant has a ticket webhook (covered by tickets.spec.ts); this one has none.
    await expect(viewer.getByRole("button", { name: "Abrir chamado", exact: true })).toHaveCount(0);
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
    await createCollection(owner, workspaceId, COLLECTION, PROVIDER);
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
    await expect(owner.getByRole("button", { name: "Abrir chamado", exact: true })).toHaveCount(0);
  });
});
