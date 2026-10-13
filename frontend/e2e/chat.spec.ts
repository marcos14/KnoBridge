import { expect, type Route, test } from "@playwright/test";

// The chat against synthetic API answers served by the browser itself: the first question of a
// new conversation streams an answer with a citation (Server-Sent Events on a POST), and the
// citation opens its source. No backend needed.
const WORKSPACE_ID = "00000000-0000-4000-8000-0000000000a1";
const ASSISTANT_ID = "00000000-0000-4000-8000-0000000000f1";
const CONVERSATION_ID = "00000000-0000-4000-8000-0000000000d1";
const QUESTION_ID = "00000000-0000-4000-8000-0000000e0001";
const ANSWER_ID = "00000000-0000-4000-8000-0000000e0002";

const citation = {
  index: 1,
  title: "Manual do caixa",
  uri: "https://docs.example.test/caixa",
  snippet: "Para fechar o caixa, confira os lançamentos do dia.",
  document_id: null,
};

const conversation = {
  id: CONVERSATION_ID,
  product_id: ASSISTANT_ID,
  product_name: "Suporte ERP",
  level: "end_user",
  user_id: "00000000-0000-4000-8000-000000000001",
  channel: "panel",
  title: "Como fecho o caixa?",
  created_at: "2026-10-10T12:00:00Z",
  updated_at: "2026-10-10T12:00:00Z",
};

const assistant = {
  id: ASSISTANT_ID,
  name: "Suporte ERP",
  description: "",
  instructions: "",
  language: "pt-BR",
  tone: "neutral",
  no_source_message: "",
  active: true,
  collection_ids: ["00000000-0000-4000-8000-0000000001a1"],
  min_similarity: 0.35,
  my_max_level: "end_user",
  created_at: "2026-10-01T00:00:00Z",
  updated_at: "2026-10-01T00:00:00Z",
};

const messageDefaults = {
  error_code: null,
  feedback: null,
  created_at: "2026-10-10T12:00:00Z",
};

const savedMessages = [
  {
    ...messageDefaults,
    id: QUESTION_ID,
    role: "user",
    content: "Como fecho o caixa?",
    status: "completed",
    citations: [],
    model: null,
    input_tokens: null,
    output_tokens: null,
    latency_ms: null,
  },
  {
    ...messageDefaults,
    id: ANSWER_ID,
    role: "assistant",
    content: "Confira os lançamentos e clique em **Fechar** [1].",
    status: "completed",
    citations: [citation],
    model: "gpt-4.1-mini",
    input_tokens: 10,
    output_tokens: 5,
    latency_ms: 20,
  },
];

function frame(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

const answerStream = [
  frame("citations", {
    message_id: ANSWER_ID,
    user_message_id: QUESTION_ID,
    citations: [citation],
  }),
  frame("delta", { text: "Confira os lançamentos e " }),
  frame("delta", { text: "clique em **Fechar** [1]." }),
  frame("done", {
    message_id: ANSWER_ID,
    status: "completed",
    model: "gpt-4.1-mini",
    input_tokens: 10,
    output_tokens: 5,
    latency_ms: 20,
  }),
].join("");

/** The workspace routes the chat calls, answered from memory: one conversation once asked. */
function workspaceApi() {
  let answered = false;
  return (route: Route) => {
    const request = route.request();
    const { pathname } = new URL(request.url());
    const base = `/v1/workspaces/${WORKSPACE_ID}`;
    if (pathname === `${base}/products`) {
      return route.fulfill({ json: { items: [assistant], total: 1, limit: 200, offset: 0 } });
    }
    if (pathname === `${base}/conversations` && request.method() === "POST") {
      return route.fulfill({ status: 201, json: { ...conversation, title: null } });
    }
    if (pathname === `${base}/conversations`) {
      const items = answered ? [conversation] : [];
      return route.fulfill({ json: { items, total: items.length, limit: 50, offset: 0 } });
    }
    if (pathname === `${base}/conversations/${CONVERSATION_ID}/messages`) {
      answered = true;
      return route.fulfill({
        status: 200,
        headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
        body: answerStream,
      });
    }
    if (pathname === `${base}/conversations/${CONVERSATION_ID}`) {
      const items = answered ? savedMessages : [];
      return route.fulfill({
        json: {
          ...conversation,
          messages: { items, total: items.length, limit: 500, offset: 0 },
        },
      });
    }
    return route.fulfill({
      status: 404,
      json: { error: { code: "not_found", message: "Not found.", details: null } },
    });
  };
}

test("test_chat_streams_an_answer_with_citation", async ({ page }) => {
  await page.route("**/v1/setup/status", (route) =>
    route.fulfill({ json: { needs_setup: false } }),
  );
  await page.route("**/v1/health/ready", (route) => route.fulfill({ json: { status: "ok" } }));
  await page.route("**/v1/me", (route) =>
    route.fulfill({
      json: {
        user: {
          id: "00000000-0000-4000-8000-000000000001",
          email: "ana@example.test",
          name: "Ana Teste",
          locale: "pt-BR",
          theme: "light",
          email_verified_at: "2026-01-01T00:00:00Z",
        },
        is_superadmin: false,
        workspaces: [
          { id: WORKSPACE_ID, name: "Acme", slug: "acme", status: "active", role: "viewer" },
        ],
      },
    }),
  );
  await page.route("**/v1/workspaces/**", workspaceApi());

  await page.goto(`/w/${WORKSPACE_ID}/chat`);
  const question = page.getByRole("textbox", { name: "Sua pergunta" });
  await expect(question).toBeFocused();
  await question.fill("Como fecho o caixa?");
  await question.press("Enter");

  await expect(page).toHaveURL(new RegExp(`/chat/${CONVERSATION_ID}$`));
  await expect(page.getByText("Fechar", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Como fecho o caixa?" })).toBeVisible();
  await page.getByRole("button", { name: "Fonte 1: Manual do caixa" }).click();

  const panel = page.getByRole("dialog", { name: "[1] Manual do caixa" });
  await expect(panel.getByText(citation.snippet)).toBeVisible();
  await expect(panel.getByRole("link", { name: "Abrir a fonte" })).toHaveAttribute(
    "rel",
    "noopener noreferrer",
  );
});
