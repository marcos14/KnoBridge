import { expect, type Locator, type Page, test } from "@playwright/test";

import {
  acceptInvitation,
  adminLogin,
  ask,
  configureLevels,
  createCollection,
  createFakeProvider,
  createFolderSource,
  createProduct,
  createWorkspace,
  issueIngestToken,
  type Level,
  LEVELS,
  NO_SOURCE_ANSWER,
  personPage,
  syncSource,
} from "./flows";

// Products and response levels end to end (plan 0009): one product answers the same question at
// the three levels, each with its own sources. A folder with a Markdown manual and a TypeScript
// file (the manual is for everyone, the code only for development and product), a folder whose
// minimum level the owner sets to support (a read-only SQL query) and a cards source fed by
// POST /v1/ingest/cards with the token made in the panel (development and product by default).
// The end user answer cites only the manual, never code; support adds the query; development and
// product adds the code and the card.
//
// Synthetic data only (rule 9): fixtures/levels/ (mounted at /sources/levels) and the card below.
const RUN = Date.now().toString(36);
const OWNER = {
  name: "Nina Níveis",
  email: `levels-owner-${RUN}@example.test`,
  password: "e2e-levels-owner-password-1",
};
const WORKSPACE = `Níveis E2E ${RUN}`;
const PROVIDER = "Fake Níveis E2E";
const COLLECTION = `Base Níveis E2E ${RUN}`;
const MANUAL_SOURCE = `Manual Níveis ${RUN}`;
const SUPPORT_SOURCE = `Consultas Níveis ${RUN}`;
const CARDS_SOURCE = `Cards Níveis ${RUN}`;
const PRODUCT = `Financeiro Níveis ${RUN}`;
const BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost:5173";
const SYNC_TIMEOUT = 120_000;

// What each source indexes (titles as the citations show them).
const MANUAL = { path: "/sources/levels/manual", documents: 2, file: "segunda-via-do-boleto.md" };
const CODE_FILE = "boleto.ts";
const SUPPORT = {
  path: "/sources/levels/suporte",
  documents: 1,
  file: "consulta-da-segunda-via.md",
};
const CARD = {
  external_id: `e2e-${RUN}-card`,
  number: `BOL-${RUN}`,
  title: "Emitir a segunda via do boleto vencido pelo portal",
  type: "feature",
  status: "done",
  url: `https://cards.example.test/BOL-${RUN}`,
  description: {
    body: "Permitir emitir a segunda via do boleto vencido pelo portal do cliente, com o vencimento atualizado.",
  },
  sprint: { name: "Sprint 42" },
  created_at: "2026-09-01T12:00:00Z",
  updated_at: "2026-09-29T18:00:00Z",
  done_at: "2026-09-29T17:40:00Z",
};
// Every term is in the manual's section, the code's comment, the query's section and the card's
// title, so the full-text arm finds all four (each only at its level).
const QUESTION = "Como emitir a segunda via do boleto?";

/** The citation button of `title` in the answer's sources ("[n] <title> …"). */
function citation(page: Page, title: string): Locator {
  const escaped = title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return page.getByRole("button", { name: new RegExp(`^\\[\\d+\\] ${escaped}`) });
}

/** Asks `QUESTION` at `level` and waits for the whole answer (the feedback shows at the end). */
async function askAt(page: Page, workspaceId: string, level: Level): Promise<void> {
  await ask(page, workspaceId, PRODUCT, QUESTION, level);
  await expect(page.getByText(`Nível: ${LEVELS[level]}`)).toBeVisible();
  await expect(page.getByRole("button", { name: "Resposta útil" })).toBeVisible();
  await expect(page.getByText(NO_SOURCE_ANSWER)).toHaveCount(0);
}

/** The value of one state in the cards inbox summary. */
function inboxCount(page: Page, state: string): Locator {
  return page
    .getByLabel("Cards recebidos por estado")
    .getByText(state, { exact: true })
    .locator("xpath=following-sibling::dd");
}

test("test_same_question_at_three_levels_uses_each_level_sources", async ({ browser, request }) => {
  // Two folder syncs, a cards sync and three answers in one flow.
  test.setTimeout(420_000);
  const admin = await personPage(browser);
  const owner = await personPage(browser);
  let workspaceId = "";
  let token = "";

  await test.step("an owner gets a workspace with the levels on the fake provider", async () => {
    await adminLogin(admin, request);
    await createWorkspace(admin, WORKSPACE, OWNER.email);
    workspaceId = await acceptInvitation(owner, OWNER);
    await createFakeProvider(owner, workspaceId, PROVIDER);
    await configureLevels(owner, workspaceId, PROVIDER);
    await createCollection(owner, workspaceId, COLLECTION, PROVIDER);
  });

  await test.step("a folder with a manual and code keeps the end user default", async () => {
    await createFolderSource(owner, workspaceId, MANUAL_SOURCE, COLLECTION, MANUAL.path);
    await syncSource(owner, MANUAL_SOURCE, MANUAL.documents);
  });

  await test.step("the owner sets the query folder to the support level", async () => {
    await createFolderSource(
      owner,
      workspaceId,
      SUPPORT_SOURCE,
      COLLECTION,
      SUPPORT.path,
      "support",
    );
    await syncSource(owner, SUPPORT_SOURCE, SUPPORT.documents);

    await owner.goto(`/w/${workspaceId}/sources`);
    const row = owner.getByRole("row").filter({ hasText: SUPPORT_SOURCE });
    await expect(row.getByText(LEVELS.support, { exact: true })).toBeVisible();
  });

  await test.step("a cards source, for development and product, gets its send token", async () => {
    await owner.goto(`/w/${workspaceId}/sources`);
    await owner.getByRole("button", { name: "Nova fonte" }).click();
    const dialog = owner.getByRole("dialog", { name: "Nova fonte" });
    await dialog.getByRole("radio", { name: "Cards de desenvolvimento" }).click();
    await dialog.getByLabel("Nome").fill(CARDS_SOURCE);
    await expect(dialog.getByRole("combobox", { name: "Coleção" })).toHaveText(COLLECTION);
    await expect(dialog.getByRole("combobox", { name: "Nível mínimo" })).toHaveText(
      `${LEVELS.product_dev} (padrão)`,
    );
    await dialog.getByRole("button", { name: "Salvar" }).click();
    await expect(owner.getByText(`Fonte ${CARDS_SOURCE} criada.`)).toBeVisible();

    await owner.getByRole("link", { name: CARDS_SOURCE }).click();
    await expect(owner.getByRole("heading", { level: 1, name: CARDS_SOURCE })).toBeVisible();
    token = await issueIngestToken(owner, CARDS_SOURCE);
  });

  await test.step("a card sent to /v1/ingest/cards is indexed", async () => {
    const response = await fetch(`${BASE_URL}/v1/ingest/cards`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ items: [{ op: "upsert", card: CARD }] }),
    });
    expect(response.status).toBe(202);
    const body = (await response.json()) as { results: { status: string }[]; sync: string };
    expect(body.results.map(({ status }) => status)).toEqual(["queued"]);
    expect(body.sync).toBe("started");

    // The summary is read once per visit: reload until the card is indexed.
    await expect(async () => {
      await owner.goto(`/w/${workspaceId}/sources`);
      await owner.getByRole("link", { name: CARDS_SOURCE }).click();
      await expect(inboxCount(owner, "Aguardando processamento")).toHaveText("0");
      await expect(inboxCount(owner, "Indexados")).toHaveText("1");
    }).toPass({ timeout: SYNC_TIMEOUT, intervals: [2_000] });
  });

  await test.step("a product answers from the collection", async () => {
    await createProduct(owner, workspaceId, PRODUCT, [COLLECTION]);
  });

  await test.step("the end user answer cites only the manual, never code", async () => {
    await askAt(owner, workspaceId, "end_user");
    await expect(citation(owner, MANUAL.file).first()).toBeVisible();
    await expect(citation(owner, CODE_FILE)).toHaveCount(0);
    await expect(citation(owner, SUPPORT.file)).toHaveCount(0);
    await expect(citation(owner, CARD.title)).toHaveCount(0);
  });

  await test.step("the support answer adds the query, still without code or cards", async () => {
    await askAt(owner, workspaceId, "support");
    await expect(citation(owner, MANUAL.file).first()).toBeVisible();
    await expect(citation(owner, SUPPORT.file).first()).toBeVisible();
    await expect(citation(owner, CODE_FILE)).toHaveCount(0);
    await expect(citation(owner, CARD.title)).toHaveCount(0);
  });

  await test.step("the development and product answer adds the code and the card", async () => {
    await askAt(owner, workspaceId, "product_dev");
    await expect(citation(owner, MANUAL.file).first()).toBeVisible();
    await expect(citation(owner, SUPPORT.file).first()).toBeVisible();
    await expect(citation(owner, CODE_FILE).first()).toBeVisible();

    // "[n] <title>", then the card's number and its status.
    const card = citation(owner, CARD.title);
    await expect(card).toHaveAccessibleName(new RegExp(`Card ${CARD.number} Concluído$`));
    await card.click();
    const panel = owner.getByRole("dialog", { name: new RegExp(CARD.title) });
    await expect(panel.getByText("Sprint 42", { exact: true })).toBeVisible();
    await expect(
      panel.getByRole("link", { name: "Abrir o card no sistema de origem" }),
    ).toHaveAttribute("href", CARD.url);
    await panel.getByRole("button", { name: "Fechar" }).click();
  });
});
