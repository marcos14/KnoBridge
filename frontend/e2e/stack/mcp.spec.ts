import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import { expect, test } from "@playwright/test";

import {
  adminLogin,
  configureLevels,
  connectTicketWebhook,
  createApiKey,
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

// The MCP server end to end (plan 0010): the superadmin creates a workspace and enters it, the
// `fake` provider answers every level, the synthetic manual folder (a Markdown manual for everyone
// and a TypeScript file only for development and product) is indexed, and the product's
// "Abrir chamado" webhook points at the fake ticket system. An API key created on the panel (end
// user, the panel's default) then drives the official TypeScript MCP SDK over Streamable HTTP at
// /v1/mcp: list_products shows the product and the levels the key reaches; search_knowledge cites
// the manual and never the code, without any LLM answer (Usage and costs counts only the `ask`);
// ask answers with the citation; open_ticket reaches the receiver with channel `mcp`; a level
// above the key's maximum is refused and a wrong key gets the 401.
//
// Synthetic data only (rule 9): fixtures/levels/manual, mounted at /sources/levels/manual.
const RUN = Date.now().toString(36);
const WORKSPACE = `MCP E2E ${RUN}`;
const OWNER_EMAIL = `mcp-owner-${RUN}@example.test`;
const PROVIDER = "Fake MCP E2E";
const COLLECTION = `Base MCP ${RUN}`;
const SOURCE = `Manual MCP ${RUN}`;
const PRODUCT = `Financeiro MCP ${RUN}`;
const API_KEY_NAME = `IDE E2E ${RUN}`;
const MANUAL = { path: "/sources/levels/manual", documents: 2, file: "segunda-via-do-boleto.md" };
const CODE_FILE = "boleto.ts";
// Every term is in the manual's section and in the code's comment (levels.spec.ts uses it too).
const QUESTION = "Como emitir a segunda via do boleto?";
const REQUESTER_EMAIL = `dev-${RUN}@example.test`;

interface Citation {
  index: number;
  title: string;
  document_id: string;
  evidence: unknown;
}

interface ToolResult {
  isError: boolean;
  data: Record<string, unknown>;
}

/**
 * Calls a tool and returns its JSON: the structured content of a result (the same JSON the text
 * part carries), or the text part of an error (`{"error": {code, message, details}}`), which has
 * no structured content (docs/specs/mcp.md, "Erros das ferramentas").
 */
async function callTool(
  client: Client,
  name: string,
  args: Record<string, unknown> = {},
): Promise<ToolResult> {
  const result = await client.callTool({ name, arguments: args });
  const [first] = result.content as { type: string; text?: string }[];
  const text = JSON.parse(first?.text ?? "{}") as Record<string, unknown>;
  if (result.isError === true) {
    expect(result.structuredContent).toBeUndefined();
    return { isError: true, data: text };
  }
  expect(result.structuredContent).toEqual(text);
  return { isError: false, data: text };
}

/** A client of the official SDK connected to the instance's /v1/mcp with `apiKey`. */
async function connect(baseURL: string, apiKey: string): Promise<Client> {
  const client = new Client({ name: "knobridge-e2e", version: "1.0.0" });
  const transport = new StreamableHTTPClientTransport(new URL(`${baseURL}/v1/mcp`), {
    requestInit: { headers: { Authorization: `Bearer ${apiKey}` } },
  });
  await client.connect(transport);
  return client;
}

function titles(citations: unknown): string[] {
  return (citations as Citation[]).map(({ title }) => title);
}

test("test_mcp_sdk_uses_the_five_tools_within_the_key_level", async ({
  browser,
  request,
  baseURL,
}) => {
  // A whole indexing run plus the panel steps: above the config's 180 s.
  test.setTimeout(300_000);
  const admin = await personPage(browser);
  let workspaceId = "";
  let apiKey = "";

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

  await test.step("an API key made on the panel shows how to connect by MCP", async () => {
    apiKey = await createApiKey(admin, workspaceId, API_KEY_NAME);
    const mcp = admin.getByRole("region", { name: "Conectar por MCP" });
    await expect(mcp.getByText(`${String(baseURL)}/v1/mcp`).first()).toBeVisible();
  });

  const client = await test.step("the SDK connects and lists the five tools", async () => {
    const connected = await connect(String(baseURL), apiKey);
    const { tools } = await connected.listTools();
    expect(tools.map(({ name }) => name).sort()).toEqual([
      "ask",
      "get_document",
      "list_products",
      "open_ticket",
      "search_knowledge",
    ]);
    return connected;
  });

  try {
    await test.step("list_products shows the product up to the key's level", async () => {
      const { isError, data } = await callTool(client, "list_products");
      expect(isError).toBe(false);
      expect(data.max_level).toBe("end_user");
      const products = data.products as {
        name: string;
        levels: string[];
        ticket_enabled: boolean;
      }[];
      const product = products.find(({ name }) => name === PRODUCT);
      expect(product?.levels).toEqual(["end_user"]);
      expect(product?.ticket_enabled).toBe(true);
    });

    let documentId = "";
    await test.step("search_knowledge cites the manual, never the code", async () => {
      const { isError, data } = await callTool(client, "search_knowledge", {
        product: PRODUCT,
        query: QUESTION,
      });
      expect(isError).toBe(false);
      expect(data.level).toBe("end_user");
      const results = data.results as { content: string; citation: Citation }[];
      const cited = results.map(({ citation }) => citation.title);
      expect(cited).toContain(MANUAL.file);
      expect(cited).not.toContain(CODE_FILE);
      expect(data.note).toBeNull();
      const manual = results.find(({ citation }) => citation.title === MANUAL.file);
      expect(manual?.citation.evidence ?? null).toBeNull();
      documentId = manual?.citation.document_id ?? "";
    });

    await test.step("get_document reads the cited manual", async () => {
      const { isError, data } = await callTool(client, "get_document", {
        product: PRODUCT,
        document_id: documentId,
      });
      expect(isError).toBe(false);
      expect((data.document as { id: string }).id).toBe(documentId);
      // The citation of the first part, as search_knowledge gave it.
      expect((data.citation as Citation).title).toBe(MANUAL.file);
      const parts = data.parts as { content: string }[];
      expect(parts.map(({ content }) => content).join("\n")).toContain("segunda via");
    });

    await test.step("a level above the key's maximum is refused", async () => {
      for (const [tool, args] of [
        ["search_knowledge", { product: PRODUCT, query: QUESTION, level: "support" }],
        ["ask", { product: PRODUCT, question: QUESTION, level: "product_dev" }],
      ] as const) {
        const { isError, data } = await callTool(client, tool, args);
        expect(isError).toBe(true);
        expect(data.error).toMatchObject({
          code: "level_not_allowed",
          details: { max_level: "end_user", reason: "api_key" },
        });
      }
    });

    let messageId = "";
    await test.step("ask answers with the manual's citation", async () => {
      const { isError, data } = await callTool(client, "ask", {
        product: PRODUCT,
        question: QUESTION,
      });
      expect(isError).toBe(false);
      expect(data.status).toBe("completed");
      expect(data.level).toBe("end_user");
      expect(titles(data.citations)).toContain(MANUAL.file);
      expect(titles(data.citations)).not.toContain(CODE_FILE);
      expect(String(data.answer).length).toBeGreaterThan(0);
      expect(data.ticket_enabled).toBe(true);
      messageId = String(data.message_id);
    });

    await test.step("open_ticket reaches the ticket system with the mcp channel", async () => {
      const { isError, data } = await callTool(client, "open_ticket", {
        message_id: messageId,
        summary: `Segunda via pelo MCP ${RUN}`,
        requester_email: REQUESTER_EMAIL,
      });
      expect(isError).toBe(false);
      expect(data.status).toBe("pending");

      await expect
        .poll(
          async () =>
            (await sinkDeliveries()).filter(
              (delivery) => delivery.requester?.email === REQUESTER_EMAIL,
            ),
          { timeout: 60_000 },
        )
        .toHaveLength(1);
      const [delivery] = (await sinkDeliveries()).filter(
        ({ requester }) => requester?.email === REQUESTER_EMAIL,
      );
      expect(delivery?.verified).toBe(true);
      expect(delivery?.channel).toBe("mcp");
      expect(delivery?.ticket_id).toMatch(/^KB-\d{4}$/);
      expect(delivery?.requester).toMatchObject({ verified: false, external_id: null });
    });
  } finally {
    await client.close();
  }

  await test.step("a wrong key gets the 401 before any tool", async () => {
    // The SDK's StreamableHTTPError carries the HTTP status in `code` and our body in the message.
    const refused = connect(String(baseURL), `kbk_00000000_${"0".repeat(43)}`);
    await expect(refused).rejects.toMatchObject({
      code: 401,
      message: expect.stringContaining("invalid_api_key"),
    });
  });

  await test.step("usage counts only the answer of ask, in the mcp channel", async () => {
    await admin.goto(`/w/${workspaceId}/usage`);
    await expect(admin.getByRole("heading", { level: 1, name: "Uso e custos" })).toBeVisible();
    await pickOption(admin, "Agrupar por", "Canal");

    const table = admin.getByRole("table", { name: "Uso por Canal" });
    await expect(table.getByRole("columnheader", { name: "Respostas" })).toBeVisible();
    const headers = await table.getByRole("columnheader").allTextContents();
    const answers = headers.findIndex((header) => header.trim() === "Respostas");
    expect(answers).toBeGreaterThan(0);
    const row = table
      .getByRole("row")
      .filter({ has: admin.getByRole("cell", { name: "MCP", exact: true }) });
    // search_knowledge and get_document never answer: one answer, the one of ask.
    await expect(row.getByRole("cell").nth(answers)).toHaveText("1");
  });

  await test.step("the conversation of ask shows under the key in Conversations", async () => {
    await admin.goto(`/w/${workspaceId}/conversations`);
    const table = admin.getByRole("table", { name: "Conversas do workspace" });
    const row = table.getByRole("row").filter({ hasText: QUESTION });
    await expect(row.getByText(`MCP · ${API_KEY_NAME}`)).toBeVisible();
  });
});
