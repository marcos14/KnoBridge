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
  editProduct,
  NO_SOURCE_ANSWER,
  personPage,
  syncSource,
} from "./flows";

// Answer quality end to end (plan 0011): an answer found in more than one search, with the
// "Buscando: …" step on the panel chat and the "N buscas" total; reranking on and off with the
// fake reranker of the E2E layer (scripts/fake_reranker.py puts the chunk with [[rerank-top]] on
// top), in "Testar busca" and in the chat citations; and the warning of a generated file that
// dominates a source's index, excluded from the panel.
//
// Synthetic data only (rule 9): fixtures/quality/ (mounted at /sources/quality).
const RUN = Date.now().toString(36);
const PROVIDER = "Fake Qualidade E2E";

// The fake LLM calls search_sources once per [[buscar: …]] marker of the question, in order
// (docs/specs/chat.md, "Fake com roteiro"); each query finds one file by full text.
const KNOWLEDGE = { path: "/sources/quality/conhecimento", documents: 4 };
const CREDIT = { query: "limite de crédito", file: "limite-de-credito.md" };
const BLOCK = { query: "bloqueio automático do pedido", file: "bloqueio-de-pedido.md" };
const STEPS_QUESTION = `Por que a venda ficou retida? [[buscar: ${CREDIT.query}]] [[buscar: ${BLOCK.query}]]`;

// Both files have every term of the question, so the hybrid search finds them, the focused one
// first. The fake reranker scores by the question's exact words: the FAQ carries the marker (1.0)
// and the focused file lacks "como", so the reranker puts the FAQ first.
const RERANK_QUESTION = "Como conciliar extrato bancário?";
const FOCUSED = "conciliacao-bancaria.md";
const FAQ = "perguntas-frequentes.md";

// A folder with a manual and a generated report of 210 sections: one chunk each, past the 200
// chunks below which nothing dominates (docs/specs/indexacao.md, "Arquivos que dominam o índice").
const GENERATED = {
  path: "/sources/quality/gerado",
  documents: 2,
  pattern: "relatorios/fechamentos-2026.md",
};

function person(prefix: string) {
  return {
    name: "Quésia Qualidade",
    email: `${prefix}-owner-${RUN}@example.test`,
    password: `e2e-${prefix}-owner-password-1`,
  };
}

/** The citation buttons of the last answer, in order ("[n] <title> …"). */
function citations(page: Page): Locator {
  return page.getByRole("button", { name: /^\[\d+\] / });
}

/** Waits for the whole answer (the feedback shows at the end), which must have sources. */
async function waitAnswer(page: Page): Promise<void> {
  await expect(page.getByRole("button", { name: "Resposta útil" })).toBeVisible();
  await expect(page.getByText(NO_SOURCE_ANSWER)).toHaveCount(0);
}

/**
 * Holds the chat stream right after its first `step` event, until `releaseStream` runs: the
 * fake LLM answers in milliseconds, so without it "Buscando: …" would come and go unseen. The
 * panel reads the stream through `fetch`; the wrapper passes everything else untouched.
 */
async function holdStreamAfterStep(page: Page): Promise<void> {
  // Runs in the page, where globalThis is the window (the e2e types know only Node globals).
  await page.addInitScript(() => {
    const original = globalThis.fetch.bind(globalThis);
    let release: () => void = () => undefined;
    const released = new Promise<void>((resolve) => {
      release = resolve;
    });
    Object.assign(globalThis, {
      releaseStream: () => {
        release();
      },
    });
    globalThis.fetch = async (...args: Parameters<typeof fetch>) => {
      const [input] = args;
      const response = await original(...args);
      const url = input instanceof Request ? input.url : String(input);
      const path = url.split("?")[0] ?? "";
      const type = response.headers.get("content-type") ?? "";
      const isChat = path.endsWith("/messages") && type.includes("text/event-stream");
      if (!isChat || response.body === null) {
        return response;
      }
      const reader = (response.body as ReadableStream<Uint8Array>).getReader();
      const decoder = new TextDecoder();
      const encoder = new TextEncoder();
      let buffer = "";
      let held = false;
      const body = new ReadableStream<Uint8Array>({
        async pull(controller) {
          const { done, value } = await reader.read();
          if (done) {
            if (buffer !== "") controller.enqueue(encoder.encode(buffer));
            controller.close();
            return;
          }
          if (held) {
            controller.enqueue(value);
            return;
          }
          buffer += decoder.decode(value, { stream: true });
          const at = buffer.indexOf("event: step");
          const end = at === -1 ? null : /\r?\n\r?\n/.exec(buffer.slice(at));
          if (at === -1) {
            // No step yet: pass every complete line on (the parser takes any split) and keep a
            // partial line, which may be the start of "event: step".
            const cut = buffer.lastIndexOf("\n") + 1;
            controller.enqueue(encoder.encode(buffer.slice(0, cut)));
            buffer = buffer.slice(cut);
            return;
          }
          if (end === null) {
            // The step event is not complete yet: wait for the blank line that ends it.
            return;
          }
          const cut = at + end.index + end[0].length;
          controller.enqueue(encoder.encode(buffer.slice(0, cut)));
          const rest = buffer.slice(cut);
          buffer = "";
          held = true;
          await released;
          if (rest !== "") controller.enqueue(encoder.encode(rest));
        },
      });
      return new Response(body, {
        status: response.status,
        statusText: response.statusText,
        headers: response.headers,
      });
    };
  });
}

/** On the collection page: "Testar busca" with the reranking `choice`, best result first. */
async function testSearch(page: Page, choice: string): Promise<Locator> {
  await page.getByRole("radio", { name: choice }).click();
  await page.getByRole("button", { name: "Buscar", exact: true }).click();
  return page.getByRole("list", { name: "Resultados da busca" }).getByRole("listitem");
}

test("test_answer_searches_again_and_reranks_citations", async ({ browser, request }) => {
  // A sync, three answers, two searches and a product edit in one flow.
  test.setTimeout(300_000);
  const owner = person("quality");
  const workspace = `Qualidade E2E ${RUN}`;
  const collection = `Base Qualidade E2E ${RUN}`;
  const source = `Conhecimento Qualidade ${RUN}`;
  const product = `Financeiro Qualidade ${RUN}`;
  const admin = await personPage(browser);
  const page = await personPage(browser);
  await holdStreamAfterStep(page);
  let workspaceId = "";

  await test.step("an owner indexes the knowledge folder for a product", async () => {
    await adminLogin(admin, request);
    await createWorkspace(admin, workspace, owner.email);
    workspaceId = await acceptInvitation(page, owner);
    await createFakeProvider(page, workspaceId, PROVIDER);
    await configureLevels(page, workspaceId, PROVIDER);
    await createCollection(page, workspaceId, collection, PROVIDER);
    await createFolderSource(page, workspaceId, source, collection, KNOWLEDGE.path);
    await syncSource(page, source, KNOWLEDGE.documents);
    await createProduct(page, workspaceId, product, [collection]);
  });

  await test.step("the answer shows each new search, then the total", async () => {
    // Development and product (the owner's maximum, preselected) allows up to 4 searches.
    await ask(page, workspaceId, product, STEPS_QUESTION);
    await expect(page.getByText(`Buscando: ${CREDIT.query}`)).toBeVisible();
    await page.evaluate(() => {
      (globalThis as unknown as { releaseStream: () => void }).releaseStream();
    });
    await waitAnswer(page);
    await expect(page.getByText(/^Buscando:/)).toHaveCount(0);

    // Both files are cited (each query of the markers finds one of them by full text).
    await expect(citations(page).filter({ hasText: CREDIT.file })).toHaveCount(1);
    await expect(citations(page).filter({ hasText: BLOCK.file })).toHaveCount(1);
    const total = page.getByText("3 buscas", { exact: true });
    await expect(total).toBeVisible();
    await total.click();
    await expect(page.getByRole("list", { name: "Buscas feitas para esta resposta" })).toHaveText(
      ["A pergunta", CREDIT.query, BLOCK.query].join(""),
    );
  });

  await test.step("a plain answer takes one search", async () => {
    await ask(page, workspaceId, product, RERANK_QUESTION);
    await waitAnswer(page);
    await expect(page.getByText("1 busca", { exact: true })).toBeVisible();
    // Reranking is on by default when the instance has a reranker: the FAQ goes first.
    await expect(citations(page).first()).toContainText(FAQ);
    await expect(citations(page).filter({ hasText: FOCUSED })).toHaveCount(1);
  });

  await test.step("Testar busca compares the order with and without the reranker", async () => {
    await page.goto(`/w/${workspaceId}/collections`);
    await page.getByRole("link", { name: collection }).click();
    await expect(page.getByRole("heading", { level: 1, name: collection })).toBeVisible();
    await page.getByLabel("Pergunta ou termos").fill(RERANK_QUESTION);

    const reranked = await testSearch(page, "Com reranker");
    await expect(page.getByText(/Reordenados pelo reranker\.$/)).toBeVisible();
    await expect(reranked.first()).toContainText(FAQ);
    await expect(reranked.first()).toContainText("Reranker 1,000");

    const plain = await testSearch(page, "Sem reranker");
    await expect(page.getByText(/Na ordem da busca híbrida, sem reranker\.$/)).toBeVisible();
    await expect(plain.first()).toContainText(FOCUSED);
    await expect(plain.first()).not.toContainText("Reranker");
  });

  await test.step("with reranking off in the product, the hybrid order comes back", async () => {
    const dialog = await editProduct(page, workspaceId, product);
    const rerank = dialog.getByRole("checkbox", { name: "Reordenar trechos" });
    await expect(rerank).toBeChecked();
    await rerank.uncheck();
    await dialog.getByRole("button", { name: "Salvar" }).click();
    await expect(page.getByText(`Produto ${product} atualizado.`)).toBeVisible();

    await ask(page, workspaceId, product, RERANK_QUESTION);
    await waitAnswer(page);
    await expect(citations(page).first()).toContainText(FOCUSED);
    await expect(citations(page).filter({ hasText: FAQ })).toHaveCount(1);
  });
});

test("test_generated_file_dominating_a_source_is_flagged_and_excluded", async ({
  browser,
  request,
}) => {
  // Two syncs (one of 211 chunks) in one flow.
  test.setTimeout(300_000);
  const owner = person("dominant");
  const workspace = `Dominantes E2E ${RUN}`;
  const collection = `Base Dominantes E2E ${RUN}`;
  const source = `Fechamentos ${RUN}`;
  const admin = await personPage(browser);
  const page = await personPage(browser);
  let workspaceId = "";

  await test.step("an owner syncs a folder with a generated report", async () => {
    await adminLogin(admin, request);
    await createWorkspace(admin, workspace, owner.email);
    workspaceId = await acceptInvitation(page, owner);
    await createFakeProvider(page, workspaceId, PROVIDER);
    await createCollection(page, workspaceId, collection, PROVIDER);
    await createFolderSource(page, workspaceId, source, collection, GENERATED.path);
    await syncSource(page, source, GENERATED.documents);
  });

  await test.step("the source list and detail flag the report", async () => {
    await page.goto(`/w/${workspaceId}/sources`);
    const row = page.getByRole("row").filter({ hasText: source });
    await expect(row.getByText("1 grupo domina o índice")).toBeVisible();

    await row.getByRole("link", { name: source }).click();
    const groups = page.getByRole("table", { name: "Grupos que dominam o índice da fonte" });
    const report = groups.getByRole("row").filter({ hasText: GENERATED.pattern });
    // Kind, files and chunks: the report's 210 sections plus its opening paragraph.
    await expect(report.getByRole("cell").nth(1)).toHaveText("Arquivo");
    await expect(report.getByRole("cell").nth(2)).toHaveText("1");
    await expect(report.getByRole("cell").nth(3)).toHaveText("211");
  });

  await test.step("excluding it and syncing again clears the warning", async () => {
    await page.getByRole("button", { name: `Excluir ${GENERATED.pattern} da fonte` }).click();
    await expect(
      page.getByText(`${GENERATED.pattern} foi para as exclusões de ${source}.`, { exact: false }),
    ).toBeVisible();
    await expect(page.getByText("Já excluído; some na próxima sincronização")).toBeVisible();

    await syncSource(page, source, 1);
    await expect(async () => {
      await page.reload();
      await expect(page.getByRole("heading", { level: 1, name: source })).toBeVisible();
      await expect(page.getByText("Arquivos que dominam o índice")).toHaveCount(0);
    }).toPass({ timeout: 30_000, intervals: [1_000] });
  });
});
