import { createHmac } from "node:crypto";
import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";

import { expect, type Locator, type Page, test } from "@playwright/test";

import {
  adminLogin,
  configureLevels,
  connectTicketWebhook,
  createCollection,
  createFakeProvider,
  createFolderSource,
  createProduct,
  createWorkspace,
  enterWorkspace,
  personPage,
  pickOption,
  syncSource,
} from "./flows";
import { sinkDeliveries } from "./webhookSink";

// The embeddable widget end to end (plan 0010): a product answers from the synthetic manual
// folder (a Markdown manual for everyone and a TypeScript file only for development and product)
// and opens tickets on the fake ticket system. The owner creates a widget on the panel, allowed on
// the origin of a test site this spec serves itself (a plain Node server on another port, so
// another origin than the instance), and generates the signing secret. The site embeds the widget
// with one <script> from the instance and the element. A visitor asks and gets the manual cited
// (never the code: always the end user level), rates the answer, opens a ticket with an e-mail
// (it reaches the receiver with channel `widget`) and finds the conversation again after a reload.
// The same site under another origin is refused, and a visitor with an identity signed by the
// site's server with the panel's secret shows by name and e-mail in Conversations.
//
// Synthetic data only (rule 9): fixtures/levels/manual, mounted at /sources/levels/manual.
const RUN = Date.now().toString(36);
const WORKSPACE = `Widget E2E ${RUN}`;
const OWNER_EMAIL = `widget-owner-${RUN}@example.test`;
const PROVIDER = "Fake Widget E2E";
const COLLECTION = `Base Widget ${RUN}`;
const SOURCE = `Manual Widget ${RUN}`;
const PRODUCT = `Financeiro Widget ${RUN}`;
const WIDGET = `Site público ${RUN}`;
const MANUAL = { path: "/sources/levels/manual", documents: 2, file: "segunda-via-do-boleto.md" };
const CODE_FILE = "boleto.ts";
// Every term is in the manual's section and in the code's comment (levels.spec.ts uses it too).
const QUESTION = "Como emitir a segunda via do boleto?";
const VISITOR_EMAIL = `visitante-${RUN}@example.test`;
const SIGNED = { sub: `cliente-${RUN}`, name: "Vera Visitante", email: `vera-${RUN}@example.test` };
const INSTANCE = process.env.E2E_BASE_URL ?? "http://localhost:5173";

/**
 * The host site: one page per path, served on a free port of this machine. `localhost:<port>` is
 * the allowed origin; `127.0.0.1:<port>` is the same site under an origin the widget refuses.
 */
const pages = new Map<string, string>();
let site: Server | undefined;
let port = 0;

function hostPage(widgetKey: string, identity?: string): string {
  const signed = identity === undefined ? "" : ` identity="${identity}"`;
  return `<!doctype html>
<html lang="pt-BR">
  <head><meta charset="utf-8" /><title>Loja Exemplo</title></head>
  <body>
    <h1>Loja Exemplo</h1>
    <script src="${INSTANCE}/widget/v1/knobridge-chat.js" defer></script>
    <knobridge-chat widget-key="${widgetKey}"${signed}></knobridge-chat>
  </body>
</html>`;
}

/** What the host's server does on every page (docs/specs/widget.md, "Identidade assinada"). */
function signIdentity(secret: string, now: number): string {
  const iat = Math.floor(now / 1000);
  const claims = { ...SIGNED, iat, exp: iat + 3600 };
  const payload = Buffer.from(JSON.stringify(claims)).toString("base64url");
  const signature = createHmac("sha256", secret).update(`v1.${payload}`).digest("hex");
  return `v1.${payload}.${signature}`;
}

test.beforeAll(async () => {
  site = createServer((request, response) => {
    const html = pages.get(new URL(request.url ?? "/", "http://site").pathname);
    response.writeHead(html === undefined ? 404 : 200, {
      "Content-Type": "text/html; charset=utf-8",
    });
    response.end(html ?? "");
  });
  await new Promise<void>((resolve) => {
    site?.listen(0, resolve);
  });
  port = (site.address() as AddressInfo).port;
});

test.afterAll(async () => {
  await new Promise<void>((resolve) => {
    if (site === undefined) {
      resolve();
      return;
    }
    site.close(() => {
      resolve();
    });
  });
});

/** Opens the bubble of the widget on `page` and returns its chat panel. */
async function openChat(page: Page): Promise<Locator> {
  await page.getByRole("button", { name: "Abrir chat de ajuda" }).click();
  return page.getByRole("dialog");
}

/** Asks `QUESTION` and waits for the whole answer (its actions show once it finishes). */
async function askWidget(chat: Locator): Promise<void> {
  const box = chat.getByRole("textbox", { name: "Sua pergunta" });
  await box.fill(QUESTION);
  await box.press("Enter");
  await expect(chat.getByRole("button", { name: "Resposta útil" })).toBeVisible();
}

/** The source "[n] <title>" in the list under the answer. */
function citation(chat: Locator, title: string): Locator {
  const escaped = title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return chat.getByRole("button", { name: new RegExp(`^\\[\\d+\\] ${escaped}$`) });
}

test("test_widget_on_another_origin_answers_rates_opens_ticket_and_keeps_history", async ({
  browser,
  request,
}) => {
  // A whole indexing run, the panel steps and the ticket polling of the widget: above 180 s.
  test.setTimeout(300_000);
  const admin = await personPage(browser);
  let workspaceId = "";
  let widgetKey = "";
  let signingSecret = "";
  const allowed = (): string => `http://localhost:${String(port)}`;

  await test.step("a product answers from the manual folder and opens tickets", async () => {
    await adminLogin(admin, request);
    await createWorkspace(admin, WORKSPACE, OWNER_EMAIL);
    workspaceId = await enterWorkspace(admin, WORKSPACE);
    await createFakeProvider(admin, workspaceId, PROVIDER);
    await configureLevels(admin, workspaceId, PROVIDER);
    await createCollection(admin, workspaceId, COLLECTION, PROVIDER);
    await createFolderSource(admin, workspaceId, SOURCE, COLLECTION, MANUAL.path);
    await syncSource(admin, SOURCE, MANUAL.documents);
    await createProduct(admin, workspaceId, PRODUCT, [COLLECTION]);
    await connectTicketWebhook(admin, workspaceId, PRODUCT);
  });

  await test.step("the owner creates the widget for the site's origin", async () => {
    await admin.goto(`/w/${workspaceId}/widgets`);
    await admin.getByRole("link", { name: "Novo widget" }).click();
    await expect(admin.getByRole("heading", { level: 1, name: "Novo widget" })).toBeVisible();
    await pickOption(admin, "Produto", PRODUCT);
    await admin.getByLabel("Nome", { exact: true }).fill(WIDGET);
    await admin.getByLabel("Origens, uma por linha").fill(allowed());
    await admin.getByRole("button", { name: "Criar widget" }).click();
    await expect(
      admin.getByText(`Widget ${WIDGET} criado. Copie o trecho abaixo para o seu site.`),
    ).toBeVisible();

    const install = admin.getByRole("region", { name: "Instalar no site" });
    const key = install.getByText(/^kbp_[a-z0-9]{24}$/);
    widgetKey = (await key.textContent())?.trim() ?? "";
    expect(widgetKey).toMatch(/^kbp_[a-z0-9]{24}$/);
    await expect(install.getByText(`${INSTANCE}/widget/v1/knobridge-chat.js`)).toBeVisible();
  });

  await test.step("the owner generates the signing secret, shown once", async () => {
    const panel = admin.getByRole("region", { name: "Identidade assinada (opcional)" });
    await panel.getByRole("button", { name: "Gerar segredo" }).click();
    const secret = panel.getByLabel("Segredo de assinatura");
    await expect(secret).toHaveText(/^kbs_[A-Za-z0-9_-]{43}$/);
    signingSecret = (await secret.textContent())?.trim() ?? "";
  });

  pages.set("/", hostPage(widgetKey));
  const visitor = await personPage(browser);

  await test.step("a visitor of the site gets the manual cited, never the code", async () => {
    await visitor.goto(`${allowed()}/`);
    const chat = await openChat(visitor);
    await askWidget(chat);
    await expect(citation(chat, MANUAL.file)).toBeVisible();
    await expect(chat.getByRole("button", { name: new RegExp(CODE_FILE) })).toHaveCount(0);
  });

  await test.step("the visitor rates the answer", async () => {
    const chat = visitor.getByRole("dialog");
    const useful = chat.getByRole("button", { name: "Resposta útil" });
    await useful.click();
    await expect(useful).toHaveAttribute("aria-pressed", "true");
  });

  let ticketId = "";
  await test.step("the visitor opens a ticket with an e-mail and it reaches the system", async () => {
    const chat = visitor.getByRole("dialog");
    await chat.getByRole("button", { name: "Abrir chamado" }).click();
    await expect(chat.getByLabel("Resumo")).toHaveValue(QUESTION);
    await chat.getByLabel("Seu e-mail").fill(VISITOR_EMAIL);
    await chat.getByRole("button", { name: "Enviar pedido" }).click();
    await expect(chat.getByText("Chamado solicitado.")).toBeVisible();

    // The widget polls the request every 10 s and shows the number once the receiver answers.
    const delivered = chat.getByText(/Chamado KB-\d{4} aberto\./);
    await expect(delivered).toBeVisible({ timeout: 70_000 });
    const received = (await sinkDeliveries()).filter(
      ({ requester }) => requester?.email === VISITOR_EMAIL,
    );
    expect(received).toHaveLength(1);
    expect(received[0]?.verified).toBe(true);
    expect(received[0]?.channel).toBe("widget");
    expect(received[0]?.requester).toMatchObject({ verified: false, external_id: null });
    ticketId = received[0]?.ticket_id ?? "";
    await expect(delivered).toContainText(`Chamado ${ticketId} aberto.`);
  });

  await test.step("after a reload, the conversation comes back from the instance", async () => {
    await visitor.reload();
    const chat = await openChat(visitor);
    // The question, with its speaker for screen readers.
    await expect(chat.getByText(`Você: ${QUESTION}`, { exact: true })).toBeVisible();
    await expect(citation(chat, MANUAL.file)).toBeVisible();
    await expect(chat.getByRole("button", { name: "Resposta útil" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(chat.getByText(`Chamado ${ticketId} aberto.`)).toBeVisible();
  });

  await test.step("the same site under an origin out of the list is refused", async () => {
    const intruder = await personPage(browser);
    // The 403 has no CORS headers, so the browser fails the request instead of handing it over.
    const config = intruder.waitForEvent("requestfailed", {
      predicate: (failed) => failed.url().endsWith(`/v1/widget/${widgetKey}/config`),
      timeout: 15_000,
    });
    await intruder.goto(`http://127.0.0.1:${String(port)}/`);
    await config;
    // Without the configuration, the bubble never shows.
    await expect(intruder.getByRole("heading", { name: "Loja Exemplo" })).toBeVisible();
    await expect(intruder.getByRole("button", { name: "Abrir chat de ajuda" })).toHaveCount(0);

    const direct = await fetch(`${INSTANCE}/v1/widget/${widgetKey}/config`, {
      headers: { Origin: "https://intruso.example.test" },
    });
    expect(direct.status).toBe(403);
    expect(direct.headers.get("access-control-allow-origin")).toBeNull();
    expect(((await direct.json()) as { error: { code: string } }).error.code).toBe(
      "widget_origin_not_allowed",
    );
  });

  await test.step("a visitor with a signed identity is known by name and e-mail", async () => {
    pages.set("/conta", hostPage(widgetKey, signIdentity(signingSecret, Date.now())));
    const known = await personPage(browser);
    await known.goto(`${allowed()}/conta`);
    const chat = await openChat(known);
    await askWidget(chat);
    await expect(citation(chat, MANUAL.file)).toBeVisible();
    // The identity carries the e-mail: the ticket form would not ask for it.
    await chat.getByRole("button", { name: "Abrir chamado" }).click();
    await expect(chat.getByLabel("Resumo")).toBeVisible();
    await expect(chat.getByLabel("Seu e-mail")).toHaveCount(0);
  });

  await test.step("Conversations shows both widget conversations and the visitors", async () => {
    await admin.goto(`/w/${workspaceId}/conversations`);
    const table = admin.getByRole("table", { name: "Conversas do workspace" });
    const rows = table.getByRole("row").filter({ hasText: `Widget · ${WIDGET}` });
    await expect(rows).toHaveCount(2);
    await expect(
      rows.filter({ hasText: `Visitante: ${SIGNED.name} (${SIGNED.email})` }),
    ).toHaveCount(1);
    const anonymous = rows.filter({ hasText: "Visitante anônimo" });
    await expect(anonymous).toHaveCount(1);
    await expect(anonymous.getByLabel("1 positivas, 0 negativas")).toBeVisible();
  });
});
