import type { ResponseLevel } from "@/lib/api/levels";

/**
 * Copyable examples of the public API (`docs/specs/api-publica.md`, "Exemplos"). The key is
 * never in them: they read it from this environment variable, so it stays out of the shell
 * history and of the code.
 */
export const API_KEY_VARIABLE = "KNOBRIDGE_API_KEY";

/**
 * What the examples talk to: the product (its id for the REST API, its name in the OpenAI
 * `model`) and the level, sent as `level` to the REST API and as `<produto>:<nível>` to the SDKs.
 */
export interface ExampleTarget {
  id: string;
  name: string;
  level: ResponseLevel;
}

const EXAMPLE_QUESTION = "Como fecho o caixa?";

/** `<server>/v1`, the base URL of the public API (the panel and the API share the origin). */
export function apiBaseUrl(serverUrl: string): string {
  return `${serverUrl.replace(/\/+$/, "")}/v1`;
}

/** The OpenAI `model` of a product in a level: `<produto>:<nível>`. */
export function exampleModel(target: ExampleTarget): string {
  return `${target.name}:${target.level}`;
}

/**
 * `curl` of the KnoBridge REST API: create a conversation in the product and level, then ask and
 * print the answer with its citations. `jq` reads the conversation id.
 */
export function restCurlExample(serverUrl: string, target: ExampleTarget): string {
  const base = apiBaseUrl(serverUrl);
  const auth = `  -H "Authorization: Bearer $${API_KEY_VARIABLE}" \\`;
  const json = '  -H "Content-Type: application/json" \\';
  const create = JSON.stringify({ product_id: target.id, level: target.level });
  const ask = JSON.stringify({ content: EXAMPLE_QUESTION, stream: false });
  return [
    "# Requires jq. The answer comes in message.content and the sources in message.citations.",
    "# Without level, the conversation uses the key's maximum level.",
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
export function openAiPythonExample(serverUrl: string, target: ExampleTarget): string {
  return [
    "import os",
    "",
    "from openai import OpenAI",
    "",
    `client = OpenAI(base_url="${apiBaseUrl(serverUrl)}", api_key=os.environ["${API_KEY_VARIABLE}"])`,
    "answer = client.chat.completions.create(",
    `    model=${JSON.stringify(exampleModel(target))},  # product:level; without :level, the key's maximum`,
    `    messages=[{"role": "user", "content": ${JSON.stringify(EXAMPLE_QUESTION)}}],`,
    ")",
    "print(answer.choices[0].message.content)",
    "# Extra KnoBridge field: the cited sources.",
    'for citation in answer.model_extra["knobridge"]["citations"]:',
    '    print(citation["index"], citation["title"], citation["uri"])',
  ].join("\n");
}

/** JavaScript (ES module) with the official OpenAI SDK, reading the `knobridge` field. */
export function openAiJavaScriptExample(serverUrl: string, target: ExampleTarget): string {
  return [
    'import OpenAI from "openai";',
    "",
    "const client = new OpenAI({",
    `  baseURL: ${JSON.stringify(apiBaseUrl(serverUrl))},`,
    `  apiKey: process.env.${API_KEY_VARIABLE},`,
    "});",
    "const answer = await client.chat.completions.create({",
    `  model: ${JSON.stringify(exampleModel(target))}, // product:level; without :level, the key's maximum`,
    `  messages: [{ role: "user", content: ${JSON.stringify(EXAMPLE_QUESTION)} }],`,
    "});",
    "console.log(answer.choices[0].message.content);",
    "// Extra KnoBridge field: the cited sources.",
    "for (const citation of answer.knobridge.citations) {",
    "  console.log(citation.index, citation.title, citation.uri);",
    "}",
  ].join("\n");
}
