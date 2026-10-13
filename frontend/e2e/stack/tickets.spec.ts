import { expect, type Locator, type Page, test } from "@playwright/test";
import { fileURLToPath } from "node:url";

import {
  acceptInvitation,
  adminLogin,
  ask,
  configureLevels,
  createCollection,
  createFakeProvider,
  createProduct,
  createWorkspace,
  editProduct,
  issueIngestToken,
  LEVELS,
  NO_SOURCE_ANSWER,
  personPage,
} from "./flows";
import { setSinkSecret, SINK_HOOK_URL, sinkDeliveries } from "./webhookSink";

// Tickets by API end to end (plan 0005), against the real stack: the owner creates a tickets
// source and its send token in the panel; the test sends a batch with the token (Node's fetch,
// as an integration would), sends it again (nothing changes) and uploads a small JSONL export;
// the `ingest` syncs index everything; the chat cites the ticket. Then the product's webhook
// points at the fake ticket system of the compose (webhook-sink), which checks the signature
// with the secret shown once: an answer without a source opens a ticket and shows its number.
//
// Synthetic data only (rule 9): the batch below and fixtures/tickets/chamados.jsonl, which is
// the output of scripts/synthetic_tickets for seed 1 and 4 tickets.
const RUN = Date.now().toString(36);
const OWNER = {
  name: "Olga Owner",
  email: `tickets-owner-${RUN}@example.test`,
  password: "e2e-owner-password-1",
};
const WORKSPACE = `Chamados E2E ${RUN}`;
const PROVIDER = "Fake E2E";
const PRODUCT = "Suporte Chamados E2E";
const COLLECTION = `Chamados E2E ${RUN}`;
const SOURCE = `Suporte E2E ${RUN}`;
const BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost:5173";
const UPLOAD_FILE = fileURLToPath(new URL("./fixtures/tickets/chamados.jsonl", import.meta.url));
const UPLOADED_TICKETS = 4;
// The two upserts of the batch, the four of the file; the delete leaves a tombstone.
const INDEXED_TICKETS = 2 + UPLOADED_TICKETS;
const SYNC_TIMEOUT = 120_000;

const CITED = {
  external_id: `e2e-${RUN}-1`,
  number: `E2E-${RUN}`,
  title: "Erro 7731 ao transmitir o SPED Contribuições",
};
// Every term is in the resolution of CITED, so the full-text arm finds it.
const QUESTION = "Como resolver o erro 7731 na transmissão do SPED Contribuições?";
// No word in common with any ticket: no source, so "Abrir chamado" (rule 8).
const UNRELATED_QUESTION = `Previsão meteorológica para Júpiter ${RUN}`;

// Names, e-mails, the phone and the CPF are made up; the CPF only has valid check digits.
const CITED_TICKET = {
  ...CITED,
  status: "resolved",
  original_status: "Resolvido pelo atendente",
  priority: "alta",
  category: "Fiscal",
  product: "Fiscal",
  tags: ["sped", "contribuições"],
  url: `https://suporte.example.test/chamados/${CITED.number}`,
  created_at: "2026-10-01T09:00:00-03:00",
  updated_at: "2026-10-01T15:00:00-03:00",
  resolved_at: "2026-10-01T14:50:00-03:00",
  requester: {
    name: "Helena Duarte",
    email: "helena.duarte@padaria.example",
    organization: "Padaria Aurora",
  },
  assignees: [{ name: "Bruno Lacerda", email: "bruno@suporte.example.test" }],
  messages: [
    {
      role: "customer",
      author_name: "Helena Duarte",
      body: "A transmissão do SPED Contribuições falha com o erro 7731. Meu telefone é (11) 98765-4321. Helena Duarte",
      created_at: "2026-10-01T09:00:00-03:00",
    },
    {
      role: "agent",
      author_name: "Bruno Lacerda",
      public: false,
      body: "CPF do titular conferido: 529.982.247-25.",
      created_at: "2026-10-01T10:00:00-03:00",
    },
  ],
  resolution: {
    body: "Como resolver o erro 7731 na transmissão do SPED Contribuições: gere a apuração do PIS e da COFINS no bloco M antes de transmitir.",
  },
};

const BATCH = {
  items: [
    { op: "upsert", ticket: CITED_TICKET },
    {
      op: "upsert",
      ticket: {
        external_id: `e2e-${RUN}-2`,
        title: "Relatório de vendas por vendedor demora a abrir",
        status: "open",
        created_at: "2026-10-02T08:00:00-03:00",
        updated_at: "2026-10-02T08:00:00-03:00",
        messages: [
          {
            role: "customer",
            body: "O relatório de vendas por vendedor leva vários minutos para abrir.",
            created_at: "2026-10-02T08:00:00-03:00",
          },
        ],
      },
    },
    { op: "delete", external_id: `e2e-${RUN}-old`, deleted_at: "2026-10-02T09:00:00Z" },
  ],
};

interface IngestResult {
  results: { index: number; status: string }[];
  counts: { queued: number; unchanged: number; stale: number; rejected: number };
  sync: string;
}

/** POST /v1/ingest/tickets with the send token, as an integration would. */
async function sendBatch(token: string): Promise<IngestResult> {
  const response = await fetch(`${BASE_URL}/v1/ingest/tickets`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify(BATCH),
  });
  expect(response.status).toBe(202);
  return (await response.json()) as IngestResult;
}

/** The value of one state in the inbox summary ("Chamados recebidos por estado"). */
function inboxCount(page: Page, state: string): Locator {
  return page
    .getByLabel("Chamados recebidos por estado")
    .getByText(state, { exact: true })
    .locator("xpath=following-sibling::dd");
}

test("test_tickets_from_api_and_upload_to_chat_and_open_ticket_by_webhook", async ({
  browser,
  request,
}) => {
  test.setTimeout(360_000);
  const admin = await personPage(browser);
  const owner = await personPage(browser);
  let workspaceId = "";
  let token = "";

  await test.step("superadmin creates a workspace for the owner, who joins", async () => {
    await adminLogin(admin, request);
    await createWorkspace(admin, WORKSPACE, OWNER.email);
    workspaceId = await acceptInvitation(owner, OWNER);
  });

  await test.step("owner sets up the fake provider, the levels, a collection and a product", async () => {
    await createFakeProvider(owner, workspaceId, PROVIDER);
    await configureLevels(owner, workspaceId, PROVIDER);
    await createCollection(owner, workspaceId, COLLECTION, PROVIDER);
    await createProduct(owner, workspaceId, PRODUCT);
  });

  await test.step("owner creates the tickets source and its send token", async () => {
    await owner.goto(`/w/${workspaceId}/sources`);
    await owner.getByRole("button", { name: "Nova fonte" }).click();
    const dialog = owner.getByRole("dialog", { name: "Nova fonte" });
    await dialog.getByRole("radio", { name: "Chamados" }).click();
    await dialog.getByLabel("Nome").fill(SOURCE);
    await expect(dialog.getByRole("combobox", { name: "Coleção" })).toHaveText(COLLECTION);
    await expect(dialog.getByRole("checkbox", { name: "Anonimizar" })).toBeChecked();
    // Tickets are for the support team and up by default.
    await expect(dialog.getByRole("combobox", { name: "Nível mínimo" })).toHaveText(
      `${LEVELS.support} (padrão)`,
    );
    await dialog.getByRole("button", { name: "Salvar" }).click();
    await expect(owner.getByText(`Fonte ${SOURCE} criada.`)).toBeVisible();

    await owner.getByRole("link", { name: SOURCE }).click();
    await expect(owner.getByRole("heading", { level: 1, name: SOURCE })).toBeVisible();
    token = await issueIngestToken(owner, SOURCE);
  });

  await test.step("the preview shows what anonymization replaces, saving nothing", async () => {
    await owner.getByRole("tab", { name: "Prévia" }).click();
    await owner.getByLabel("Chamado (JSON)").fill(JSON.stringify(CITED_TICKET));
    await owner.getByRole("button", { name: "Gerar prévia" }).click();

    const result = owner.getByRole("region", { name: `Prévia: ${CITED.title}` });
    await expect(result.getByText("Com anonimização. Notas internas fora.")).toBeVisible();
    await expect(
      result.getByRole("list", { name: "Marcadores aplicados" }).getByRole("listitem"),
    ).toHaveText(["[TELEFONE] × 1", "[SOLICITANTE] × 1"]);
    const markdown = result.getByLabel("Markdown do chamado");
    await expect(markdown).toContainText("Meu telefone é [TELEFONE]. [SOLICITANTE]");
    await expect(markdown).not.toContainText("98765-4321");
    await expect(markdown).not.toContainText("529.982.247-25");
  });

  await test.step("an integration sends a batch with the token, then sends it again", async () => {
    const first = await sendBatch(token);
    expect(first.results.map((result) => result.status)).toEqual(["queued", "queued", "queued"]);
    expect(first.sync).toBe("started");

    // Resending is safe: the same content comes back unchanged and starts nothing.
    const again = await sendBatch(token);
    expect(again.counts).toEqual({ queued: 0, unchanged: 3, stale: 0, rejected: 0 });
    expect(again.sync).toBe("none");
  });

  await test.step("owner uploads a JSONL export of synthetic tickets", async () => {
    await owner.getByRole("tab", { name: "Upload" }).click();
    await owner.getByLabel("Arquivo", { exact: true }).setInputFiles(UPLOAD_FILE);
    await owner.getByRole("button", { name: "Enviar arquivo" }).click();
    const report = owner.getByRole("region", { name: "Resultado do envio" });
    await expect(report.getByRole("status")).toContainText(
      `${String(UPLOADED_TICKETS)} itens lidos do arquivo JSONL.`,
    );
    await expect(report.getByText("Recusados").locator("xpath=following-sibling::*")).toHaveText(
      "0",
    );
  });

  await test.step("the ingest syncs index every ticket and apply the removal", async () => {
    // The summary is read once per visit: reload until the inbox has nothing waiting.
    await expect(async () => {
      await owner.goto(`/w/${workspaceId}/sources`);
      await owner.getByRole("link", { name: SOURCE }).click();
      await expect(inboxCount(owner, "Aguardando processamento")).toHaveText("0");
      await expect(inboxCount(owner, "Remoções aguardando")).toHaveText("0");
      await expect(inboxCount(owner, "Indexados")).toHaveText(String(INDEXED_TICKETS));
      await expect(inboxCount(owner, "Removidos")).toHaveText("1");
    }).toPass({ timeout: SYNC_TIMEOUT, intervals: [2_000] });
    await expect(owner.getByText(/falh(ou|aram) no último processamento/)).toHaveCount(0);
  });

  await test.step("owner links the collection and the ticket webhook to the product", async () => {
    const dialog = await editProduct(owner, workspaceId, PRODUCT);
    await dialog.getByRole("checkbox", { name: COLLECTION }).check();
    await dialog.getByRole("checkbox", { name: 'Oferecer "Abrir chamado" no chat' }).check();
    await dialog.getByLabel("URL do webhook").fill(SINK_HOOK_URL);
    await dialog.getByRole("button", { name: "Salvar" }).click();
    await expect(owner.getByText(`Produto ${PRODUCT} atualizado.`)).toBeVisible();
  });

  await test.step("owner generates the webhook secret and the test delivery passes", async () => {
    await owner.getByRole("button", { name: `Editar ${PRODUCT}` }).click();
    const dialog = owner.getByRole("dialog", { name: "Editar produto" });
    const panel = dialog.getByRole("region", { name: "Segredo e teste do webhook" });
    await panel.getByRole("button", { name: "Gerar segredo" }).click();
    const secret = dialog.getByLabel("Segredo do webhook");
    await expect(secret).toHaveText(/^kbw_/);
    await setSinkSecret((await secret.textContent()) ?? "");

    await panel.getByRole("button", { name: "Testar entrega" }).click();
    await expect(panel.getByRole("status")).toContainText("O destino aceitou a entrega de teste.");
    await dialog.getByRole("button", { name: "Cancelar" }).click();
    await expect(dialog).toBeHidden();
  });

  await test.step("owner asks about the ticket and opens the citation", async () => {
    await ask(owner, workspaceId, PRODUCT, QUESTION);

    // The list of sources: "[n] <title>" followed by the ticket number and its status.
    const cited = owner.getByRole("button", {
      name: new RegExp(`^\\[\\d+\\] ${CITED.title} Chamado ${CITED.number} Resolvido$`),
    });
    await expect(cited).toBeVisible();
    await expect(owner.getByText(NO_SOURCE_ANSWER)).toHaveCount(0);
    await cited.click();
    const panel = owner.getByRole("dialog", { name: new RegExp(`^\\[\\d+\\] ${CITED.title}$`) });
    await expect(panel.getByText(CITED.number, { exact: true })).toBeVisible();
    await expect(panel.getByText("Resolvido", { exact: true })).toBeVisible();
    await expect(
      panel.getByRole("link", { name: "Abrir o chamado no sistema de origem" }),
    ).toHaveAttribute("href", `https://suporte.example.test/chamados/${CITED.number}`);
    await panel.getByRole("button", { name: "Fechar" }).click();
  });

  await test.step("an answer without a source opens a ticket through the webhook", async () => {
    await ask(owner, workspaceId, PRODUCT, UNRELATED_QUESTION);
    await expect(owner.getByText(NO_SOURCE_ANSWER)).toBeVisible();

    await owner.getByRole("button", { name: "Abrir chamado", exact: true }).click();
    const dialog = owner.getByRole("dialog", { name: "Abrir chamado" });
    await expect(dialog.getByRole("blockquote")).toHaveText(UNRELATED_QUESTION);
    await expect(dialog.getByLabel("Resumo")).not.toHaveValue("");
    await dialog.getByRole("button", { name: "Confirmar e abrir chamado" }).click();

    const delivered = owner.getByText(/^Chamado KB-\d{4} aberto\.$/);
    await expect(delivered).toBeVisible({ timeout: 60_000 });
    await expect(owner.getByRole("link", { name: "Abrir o chamado" })).toHaveAttribute(
      "href",
      /^https:\/\/chamados\.example\.test\/KB-\d{4}$/,
    );

    // The sink got it signed with the secret, and answered the number the chat shows.
    const received = (await sinkDeliveries()).filter(
      (delivery) => delivery.question === UNRELATED_QUESTION,
    );
    expect(received).toHaveLength(1);
    expect(received[0]?.verified).toBe(true);
    await expect(delivered).toHaveText(`Chamado ${received[0]?.ticket_id ?? ""} aberto.`);
  });
});
