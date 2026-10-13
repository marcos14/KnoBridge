import { expect, type Page, test } from "@playwright/test";

import {
  acceptInvitation,
  adminLogin,
  ask,
  configureLevels,
  createCollection,
  createFakeProvider,
  createProduct,
  createWorkspace,
  NO_SOURCE_ANSWER,
  personPage,
  pickOption,
} from "./flows";
import { createSyntheticRepository, LocalRunner, removeRepository } from "./localRunner";

// The code harness end to end (plan 0004): the owner creates a runner in the panel and the real
// `knobridge-runner` starts on this host with the token, serving a synthetic Git repository; it
// comes online, the owner creates a runner source, the runner's report brings the modules, one
// module runs (the fake Claude Code of runner/tests/fakes, verified for real against the
// checkout), its rule shows up for review, the owner approves it, the harness sync indexes it and
// the chat (fake provider) answers citing the knowledge item, sealed as reviewed.
//
// Every address and every line of code is synthetic. The runner process is stopped at the end.
const RUN = Date.now().toString(36);
const OWNER = {
  name: "Rita Runner",
  email: `runner-owner-${RUN}@example.test`,
  password: "e2e-runner-owner-password-1",
};
const WORKSPACE = `Harness E2E ${RUN}`;
const PROVIDER = "Fake Harness E2E";
const COLLECTION = `Conhecimento E2E ${RUN}`;
const PRODUCT = "Suporte Harness E2E";
const RUNNER = `notebook-e2e-${RUN}`;
const REPOSITORY = "erp-e2e";
const SOURCE = `ERP E2E ${RUN}`;
// The only module the runner suggests for the synthetic repository (folder src/).
const MODULE = "src";
// What the fake agent writes (runner/tests/fakes/fake_harness.py, DEFAULT_OUTPUT).
const RULE = "Regra sintetica";
const RULE_KEY = `${MODULE}.R001`;
// Every term is in the rule's statement, so the full-text arm finds its chunk.
const QUESTION = "O valor precisa ser positivo?";
// The runner reports a new source at its next heartbeat (every 30 s) and indexing runs in the
// worker: generous, but bounded.
const REPORT_TIMEOUT = 90_000;
const JOB_TIMEOUT = 90_000;
const SYNC_TIMEOUT = 120_000;

let runner: LocalRunner | undefined;
let checkout: string | undefined;

test.afterAll(async () => {
  await runner?.stop();
  if (checkout !== undefined) {
    removeRepository(checkout);
  }
});

/** Opens a tab of the runner source's detail by its query string, as a reload would. */
async function openTab(page: Page, workspaceId: string, sourceId: string, tab: string) {
  await page.goto(`/w/${workspaceId}/sources/${sourceId}?tab=${tab}`);
  await expect(page.getByRole("heading", { level: 1, name: SOURCE })).toBeVisible();
}

test("test_runner_maps_code_into_cited_knowledge", async ({ browser, request, baseURL }, info) => {
  // A runner heartbeat, a harness job and two indexing runs in one flow.
  test.setTimeout(420_000);
  const admin = await personPage(browser);
  const owner = await personPage(browser);
  let workspaceId = "";
  let sourceId = "";
  let token = "";

  await test.step("an owner gets a workspace with the fake provider and a product", async () => {
    await adminLogin(admin, request);
    await createWorkspace(admin, WORKSPACE, OWNER.email);
    workspaceId = await acceptInvitation(owner, OWNER);
    await createFakeProvider(owner, workspaceId, PROVIDER);
    await configureLevels(owner, workspaceId, PROVIDER);
    await createCollection(owner, workspaceId, COLLECTION, PROVIDER);
    await createProduct(owner, workspaceId, PRODUCT, [COLLECTION]);
  });

  await test.step("owner creates a runner and copies its token, shown once", async () => {
    await owner.goto(`/w/${workspaceId}/runners`);
    await owner.getByRole("button", { name: "Novo runner" }).click();
    const dialog = owner.getByRole("dialog", { name: "Novo runner" });
    await dialog.getByLabel("Nome").fill(RUNNER);
    await dialog.getByRole("button", { name: "Criar runner" }).click();

    const created = owner.getByRole("dialog", { name: `Runner ${RUNNER} criado` });
    const shown = created.getByRole("region", { name: "Token do runner" }).locator("code");
    await expect(shown).toHaveText(/^kbr_[a-z0-9]{8}_[A-Za-z0-9_-]{43}$/);
    token = (await shown.textContent()) ?? "";
    await created.getByRole("button", { name: "Concluído" }).click();
    await expect(created).toBeHidden();
  });

  await test.step("the runner starts on this host and comes online", async () => {
    checkout = createSyntheticRepository();
    runner = LocalRunner.start({
      serverUrl: new URL(String(baseURL)).origin,
      token,
      repository: REPOSITORY,
      checkout,
      logFile: info.outputPath("runner.log"),
    });

    // The list refreshes every 30 s; reloading shows the first heartbeat sooner.
    const row = owner
      .getByRole("table", { name: "Runners do workspace" })
      .getByRole("row")
      .filter({ hasText: RUNNER });
    await expect(async () => {
      await owner.reload();
      await expect(row).toContainText("Online", { timeout: 2_000 });
    }).toPass({ timeout: 60_000 });
    await expect(row).toContainText("Claude Code");
    await expect(row).toContainText(REPOSITORY);
  });

  await test.step("owner creates a runner source for the served repository", async () => {
    await owner.goto(`/w/${workspaceId}/sources`);
    await owner.getByRole("button", { name: "Nova fonte" }).click();
    const dialog = owner.getByRole("dialog", { name: "Nova fonte" });
    await dialog.getByLabel("Nome").fill(SOURCE);
    await expect(dialog.getByRole("combobox", { name: "Coleção" })).toHaveText(COLLECTION);
    await dialog.getByRole("radio", { name: "Runner local" }).click();
    await pickOption(owner, "Runner", RUNNER);
    await pickOption(owner, "Repositório", REPOSITORY);
    await dialog.getByRole("button", { name: "Salvar" }).click();
    await expect(owner.getByText(`Fonte ${SOURCE} criada.`)).toBeVisible();

    await owner.getByRole("link", { name: SOURCE }).click();
    await expect(owner.getByRole("heading", { level: 1, name: SOURCE })).toBeVisible();
    sourceId = String(/\/sources\/([0-9a-f-]{36})/.exec(owner.url())?.[1]);
    await owner.getByRole("button", { name: "Testar conexão" }).click();
    await expect(owner.getByText(`A fonte ${SOURCE} está acessível.`)).toBeVisible();
  });

  await test.step("the runner's report brings the module, which the owner runs", async () => {
    const select = owner.getByRole("checkbox", { name: `Selecionar ${MODULE}` });
    await expect(async () => {
      await openTab(owner, workspaceId, sourceId, "modules");
      await expect(select).toBeVisible({ timeout: 2_000 });
    }).toPass({ timeout: REPORT_TIMEOUT });
    await expect(owner.getByText("2 arquivos · 8 linhas")).toBeVisible();

    await select.check();
    await owner.getByRole("button", { name: "Rodar 1 módulo" }).click();
    await expect(owner.getByText("1 tarefa na fila.")).toBeVisible();
  });

  await test.step("the job runs on the runner and succeeds", async () => {
    await openTab(owner, workspaceId, sourceId, "jobs");
    // The tab polls while the job is active; wait for a final status, then require success.
    const job = owner
      .getByRole("table", { name: "Tarefas da fonte" })
      .getByRole("row")
      .filter({ hasText: MODULE })
      .first();
    await expect(job).toContainText(/Concluída|Falhou|Cancelada|Adiada/, {
      timeout: JOB_TIMEOUT,
    });
    await expect(job).toContainText("Concluída");
  });

  await test.step("owner reviews the rule with its verified evidence and approves it", async () => {
    await openTab(owner, workspaceId, sourceId, "knowledge");
    await pickOption(owner, "Módulo", MODULE);
    const rule = owner.getByRole("article", { name: RULE });
    await expect(rule).toContainText(RULE_KEY);
    await expect(rule).toContainText("Inferido");
    await expect(rule).toContainText("src/rules.py");

    await rule.getByRole("button", { name: `Aprovar ${RULE}` }).click();
    await expect(owner.getByText(`${RULE} aprovado: o selo agora é revisado.`)).toBeVisible();
    await expect(rule).toContainText("Revisado");
  });

  await test.step("the harness syncs index the approved knowledge", async () => {
    // One sync after the job result and one after the approval (run after the first if it was
    // still going): wait until both are there and the newest one is final, then require success.
    const runs = owner.getByRole("table", { name: "Execuções da fonte" }).getByRole("row");
    await expect(async () => {
      await openTab(owner, workspaceId, sourceId, "indexing");
      await expect(runs).toHaveCount(3, { timeout: 2_000 });
      await expect(runs.nth(1).getByRole("cell").first()).toHaveText(/Concluída|Falhou|Cancelada/, {
        timeout: 2_000,
      });
    }).toPass({ timeout: SYNC_TIMEOUT });
    await expect(runs.nth(1).getByRole("cell").first()).toHaveText("Concluída");
    await expect(runs.nth(1)).toContainText("Harness");
  });

  await test.step("the chat answers citing the reviewed knowledge item", async () => {
    await ask(owner, workspaceId, PRODUCT, QUESTION);

    // "[n] <title>", then the first evidence and the seal.
    const cited = owner.getByRole("button", {
      name: new RegExp(`^\\[\\d+\\] ${RULE}.*Revisado`),
    });
    await expect(cited.first()).toBeVisible();
    await expect(owner.getByText(NO_SOURCE_ANSWER)).toHaveCount(0);
    await cited.first().click();
    const panel = owner.getByRole("dialog", { name: new RegExp(RULE) });
    await expect(panel.getByText(RULE_KEY, { exact: true })).toBeVisible();
    await expect(panel.getByText("Evidências no código")).toBeVisible();
    await expect(panel.getByText(/src\/rules\.py/).first()).toBeVisible();
    await panel.getByRole("button", { name: "Fechar" }).click();
  });
});
