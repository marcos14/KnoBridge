/**
 * Copyable examples of the public API (`docs/specs/api-publica.md`, "Exemplos"). The key is
 * never in them: they read it from this environment variable, so it stays out of the shell
 * history and of the code.
 */
export const API_KEY_VARIABLE = "KNOBRIDGE_API_KEY";

/** The assistant the examples talk to: its id for the REST API, its name as the OpenAI model. */
export interface ExampleAssistant {
  id: string;
  name: string;
}

const EXAMPLE_QUESTION = "Como fecho o caixa?";

/** `<server>/v1`, the base URL of the public API (the panel and the API share the origin). */
export function apiBaseUrl(serverUrl: string): string {
  return `${serverUrl.replace(/\/+$/, "")}/v1`;
}

/**
 * `curl` of the KnoBridge REST API: create a conversation, then ask and print the answer with its
 * citations. `jq` reads the conversation id.
 */
export function restCurlExample(serverUrl: string, assistant: ExampleAssistant): string {
  const base = apiBaseUrl(serverUrl);
  const auth = `  -H "Authorization: Bearer $${API_KEY_VARIABLE}" \\`;
  const json = '  -H "Content-Type: application/json" \\';
  const create = JSON.stringify({ assistant_id: assistant.id });
  const ask = JSON.stringify({ content: EXAMPLE_QUESTION, stream: false });
  return [
    "# Requires jq. The answer comes in message.content and the sources in message.citations.",
    `CONVERSATION_ID=$(curl -s -X POST "${base}/conversations" \\`,
    auth,
    json,
    `  -d '${create}' | jq -r .id)`,
    "",
    `curl -s -X POST "${base}/conversations/$CONVERSATION_ID/messages" \\`,
    auth,
    json,
    `  -d '${ask}' | jq '{content: .message.content, citations: .message.citations}'`,
  ].join("\n");
}

/** Python with the official OpenAI SDK, reading the citations from the `knobridge` field. */
export function openAiPythonExample(serverUrl: string, assistant: ExampleAssistant): string {
  return [
    "import os",
    "",
    "from openai import OpenAI",
    "",
    `client = OpenAI(base_url="${apiBaseUrl(serverUrl)}", api_key=os.environ["${API_KEY_VARIABLE}"])`,
    "answer = client.chat.completions.create(",
    `    model=${JSON.stringify(assistant.name)},`,
    `    messages=[{"role": "user", "content": ${JSON.stringify(EXAMPLE_QUESTION)}}],`,
    ")",
    "print(answer.choices[0].message.content)",
    "# Extra KnoBridge field: the cited sources.",
    'for citation in answer.model_extra["knobridge"]["citations"]:',
    '    print(citation["index"], citation["title"], citation["uri"])',
  ].join("\n");
}

/** JavaScript (ES module) with the official OpenAI SDK, reading the `knobridge` field. */
export function openAiJavaScriptExample(serverUrl: string, assistant: ExampleAssistant): string {
  return [
    'import OpenAI from "openai";',
    "",
    "const client = new OpenAI({",
    `  baseURL: ${JSON.stringify(apiBaseUrl(serverUrl))},`,
    `  apiKey: process.env.${API_KEY_VARIABLE},`,
    "});",
    "const answer = await client.chat.completions.create({",
    `  model: ${JSON.stringify(assistant.name)},`,
    `  messages: [{ role: "user", content: ${JSON.stringify(EXAMPLE_QUESTION)} }],`,
    "});",
    "console.log(answer.choices[0].message.content);",
    "// Extra KnoBridge field: the cited sources.",
    "for (const citation of answer.knobridge.citations) {",
    "  console.log(citation.index, citation.title, citation.uri);",
    "}",
  ].join("\n");
}
