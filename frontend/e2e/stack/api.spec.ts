import { expect, test } from "@playwright/test";
import OpenAI from "openai";
import type { ChatCompletionCreateParamsStreaming } from "openai/resources/chat/completions";

import {
  adminLogin,
  createAssistant,
  createCollection,
  createFakeProvider,
  createFolderSource,
  createWorkspace,
  enterWorkspace,
  KNOWLEDGE,
  personPage,
  pickOption,
  syncSource,
} from "./flows";

// The public API end to end (plan 0008): the superadmin creates a workspace, enters it from the
// instance administration, indexes the synthetic folder and creates an assistant on the `fake`
// provider (no network) that answers from it. An API key created on the panel then drives the
// official `openai` SDK for Node against the OpenAI-compatible API: the assistant is a model, and
// the answers, with and without streaming, carry the citations in the `knobridge` extension
// field. Finally, Usage and costs counts both answers in the `api` channel.
//
// Everything gets a per-run suffix, so a rerun never collides with what an earlier run left.
const RUN = Date.now().toString(36);
const WORKSPACE = `API E2E ${RUN}`;
const OWNER_EMAIL = `api-owner-${RUN}@example.test`;
const PROVIDER = "Fake API E2E";
const COLLECTION = `Base API ${RUN}`;
const SOURCE = `Manual API ${RUN}`;
const ASSISTANT = `Suporte API ${RUN}`;
const API_KEY_NAME = `Portal E2E ${RUN}`;

/** The KnoBridge extension field of a completion or chunk (docs/specs/api-publica.md). */
interface Knobridge {
  conversation_id?: string;
  message_id?: string;
  status?: string;
  citations?: { index: number; title: string; uri: string | null }[];
  cost_usd?: number | null;
}

function knobridgeOf(value: object): Knobridge | undefined {
  // The SDK keeps unknown response fields on the object; its types do not declare them.
  return (value as { knobridge?: Knobridge }).knobridge;
}

function citedTitles(extra: Knobridge | undefined): string[] {
  return (extra?.citations ?? []).map(({ title }) => title);
}

test("test_api_key_drives_the_openai_sdk_and_counts_in_usage", async ({
  browser,
  request,
  baseURL,
}) => {
  // A whole indexing run plus the panel steps: above the config's 180 s.
  test.setTimeout(300_000);
  const admin = await personPage(browser);
  let workspaceId = "";
  let apiKey = "";

  await test.step("superadmin creates a workspace and enters it", async () => {
    await adminLogin(admin, request);
    await createWorkspace(admin, WORKSPACE, OWNER_EMAIL);
    workspaceId = await enterWorkspace(admin, WORKSPACE);
  });

  await test.step("an assistant on the fake provider answers from the indexed folder", async () => {
    await createFakeProvider(admin, workspaceId, PROVIDER);
    await createCollection(admin, workspaceId, COLLECTION, PROVIDER);
    await createFolderSource(admin, workspaceId, SOURCE, COLLECTION, KNOWLEDGE.path);
    await syncSource(admin, SOURCE, KNOWLEDGE.documents);
    await createAssistant(admin, workspaceId, ASSISTANT, PROVIDER, [COLLECTION]);
  });

  await test.step("an API key is created on the panel and shown once", async () => {
    await admin.goto(`/w/${workspaceId}/api-keys`);
    await admin.getByRole("button", { name: "Nova chave" }).click();
    const dialog = admin.getByRole("dialog", { name: "Nova chave de API" });
    await dialog.getByLabel("Nome").fill(API_KEY_NAME);
    await dialog.getByRole("button", { name: "Salvar" }).click();

    const secret = admin.getByRole("dialog", { name: `Chave ${API_KEY_NAME} criada` });
    const key = secret.getByText(/^kbk_[a-z0-9]{8}_/);
    await expect(key).toBeVisible();
    apiKey = (await key.textContent())?.trim() ?? "";
    expect(apiKey).toMatch(/^kbk_[a-z0-9]{8}_[A-Za-z0-9_-]{43}$/);
    await secret.getByRole("button", { name: "Concluído" }).click();

    const row = admin.getByRole("row").filter({ hasText: API_KEY_NAME });
    await expect(row.getByText("Todos os assistentes")).toBeVisible();
    await expect(row.getByText("Nunca usada")).toBeVisible();
  });

  const client = () =>
    // No retries: each repeated request would be a new conversation.
    new OpenAI({ baseURL: `${String(baseURL)}/v1`, apiKey, maxRetries: 0 });

  await test.step("the SDK lists the assistant as a model", async () => {
    const models = await client().models.list();
    expect(models.data.map(({ id }) => id)).toContain(ASSISTANT);
  });

  await test.step("without streaming, the answer cites the file in text and in knobridge", async () => {
    const answer = await client().chat.completions.create({
      model: ASSISTANT,
      messages: [{ role: "user", content: KNOWLEDGE.question }],
    });

    const extra = knobridgeOf(answer);
    expect(extra?.status).toBe("completed");
    expect(citedTitles(extra)).toContain(KNOWLEDGE.file);
    expect(answer.model).toBe(ASSISTANT);
    expect(answer.choices[0]?.finish_reason).toBe("stop");
    // The sources footer is on by default.
    const content = answer.choices[0]?.message.content ?? "";
    expect(content).toContain("\n\nFontes:\n");
    expect(content).toContain(KNOWLEDGE.file);
  });

  await test.step("with streaming, the citations come first and the footer can be off", async () => {
    const params: ChatCompletionCreateParamsStreaming & {
      knobridge: { append_sources: boolean };
    } = {
      model: ASSISTANT,
      messages: [{ role: "user", content: KNOWLEDGE.question }],
      stream: true,
      stream_options: { include_usage: true },
      knobridge: { append_sources: false },
    };
    const stream = await client().chat.completions.create(params);

    const extras: Knobridge[] = [];
    let content = "";
    let finishReason: string | null = null;
    let sawUsage = false;
    for await (const chunk of stream) {
      const extra = knobridgeOf(chunk);
      if (extra !== undefined) {
        extras.push(extra);
      }
      const choice = chunk.choices[0];
      content += choice?.delta.content ?? "";
      finishReason = choice?.finish_reason ?? finishReason;
      sawUsage ||= chunk.choices.length === 0 && chunk.usage !== null;
    }

    expect(citedTitles(extras[0])).toContain(KNOWLEDGE.file);
    expect(extras.at(-1)?.status).toBe("completed");
    expect(finishReason).toBe("stop");
    expect(sawUsage).toBe(true);
    expect(content.length).toBeGreaterThan(0);
    expect(content).not.toContain("Fontes:");
  });

  await test.step("a wrong key gets the OpenAI 401", async () => {
    const wrong = new OpenAI({
      baseURL: `${String(baseURL)}/v1`,
      apiKey: `kbk_00000000_${"0".repeat(43)}`,
      maxRetries: 0,
    });
    await expect(wrong.models.list()).rejects.toMatchObject({
      status: 401,
      code: "invalid_api_key",
    });
  });

  await test.step("the key shows its last use", async () => {
    await admin.goto(`/w/${workspaceId}/api-keys`);
    const row = admin.getByRole("row").filter({ hasText: API_KEY_NAME });
    await expect(row.getByText("Todos os assistentes")).toBeVisible();
    await expect(row.getByText("Nunca usada")).toHaveCount(0);
  });

  await test.step("usage and costs counts both answers in the api channel", async () => {
    await admin.goto(`/w/${workspaceId}/usage`);
    await expect(admin.getByRole("heading", { level: 1, name: "Uso e custos" })).toBeVisible();
    await pickOption(admin, "Agrupar por", "Canal");

    const table = admin.getByRole("table", { name: "Uso por Canal" });
    // The headers carry a sort icon, so match the name loosely; wait for the table to render.
    await expect(table.getByRole("columnheader", { name: "Respostas" })).toBeVisible();
    const headers = await table.getByRole("columnheader").allTextContents();
    const answers = headers.findIndex((header) => header.trim() === "Respostas");
    expect(answers).toBeGreaterThan(0);
    const api = table
      .getByRole("row")
      .filter({ has: admin.getByRole("cell", { name: "API", exact: true }) });
    await expect(api.getByRole("cell").nth(answers)).toHaveText("2");
    const panel = table
      .getByRole("row")
      .filter({ has: admin.getByRole("cell", { name: "Painel", exact: true }) });
    await expect(panel.getByRole("cell").nth(answers)).toHaveText("0");
  });
});
