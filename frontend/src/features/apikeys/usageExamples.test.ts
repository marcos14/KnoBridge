import { describe, expect, it } from "vitest";

import {
  apiBaseUrl,
  exampleModel,
  openAiJavaScriptExample,
  openAiPythonExample,
  restCurlExample,
} from "./usageExamples";

const SERVER = "https://kb.example.test/";
const TARGET = {
  id: "6f1c0000-0000-4000-8000-000000000001",
  name: 'Suporte "ERP"',
  level: "support" as const,
};

describe("apiBaseUrl", () => {
  it("test_api_base_url_appends_v1_without_double_slash", () => {
    expect(apiBaseUrl(SERVER)).toBe("https://kb.example.test/v1");
    expect(apiBaseUrl("http://localhost:5173")).toBe("http://localhost:5173/v1");
  });
});

describe("exampleModel", () => {
  it("test_example_model_is_product_colon_level", () => {
    expect(exampleModel({ ...TARGET, name: "ERP", level: "end_user" })).toBe("ERP:end_user");
  });
});

describe("restCurlExample", () => {
  it("test_rest_curl_example_creates_a_conversation_in_the_level_with_the_key_from_the_environment", () => {
    const curl = restCurlExample(SERVER, TARGET);
    const lines = curl.split("\n");

    expect(lines[2]).toBe(
      'CONVERSATION_ID=$(curl -s -X POST "https://kb.example.test/v1/conversations" \\',
    );
    expect(curl).toContain('  -H "Authorization: Bearer $KNOBRIDGE_API_KEY" \\');
    expect(curl).toContain(`  -d '{"product_id":"${TARGET.id}","level":"support"}' | jq -r .id)`);
    expect(curl).toContain(
      'curl -s -X POST "https://kb.example.test/v1/conversations/$CONVERSATION_ID/messages" \\',
    );
    expect(curl).toContain('"content":"Como fecho o caixa?","stream":false');
    expect(curl).toContain("citations: .message.citations");
    expect(curl).not.toMatch(/kbk_/);
  });
});

describe("openAiPythonExample", () => {
  it("test_openai_python_example_uses_the_server_the_product_level_and_reads_the_citations", () => {
    const python = openAiPythonExample(SERVER, TARGET);

    expect(python).toContain(
      'client = OpenAI(base_url="https://kb.example.test/v1", api_key=os.environ["KNOBRIDGE_API_KEY"])',
    );
    expect(python).toContain('    model="Suporte \\"ERP\\":support",');
    expect(python).toContain('answer.model_extra["knobridge"]["citations"]');
    expect(python).not.toMatch(/kbk_/);
  });
});

describe("openAiJavaScriptExample", () => {
  it("test_openai_javascript_example_uses_the_server_the_product_level_and_reads_the_citations", () => {
    const js = openAiJavaScriptExample(SERVER, TARGET);

    expect(js).toContain('  baseURL: "https://kb.example.test/v1",');
    expect(js).toContain("  apiKey: process.env.KNOBRIDGE_API_KEY,");
    expect(js).toContain('  model: "Suporte \\"ERP\\":support",');
    expect(js).toContain("for (const citation of answer.knobridge.citations) {");
    expect(js).not.toMatch(/kbk_/);
  });
});
