import { describe, expect, it } from "vitest";

import { ingestCurl, ingestPython } from "./ingestExamples";
import { parsePushSourceTab } from "./tabs";

const SERVER = "https://kb.example.test/";

function curlBody(curl: string): unknown {
  // The body between the single quotes is the API's JSON.
  return JSON.parse(/-d '(?<body>[\s\S]+)'$/.exec(curl)?.groups?.body ?? "");
}

describe("ingestCurl", () => {
  it("test_ingest_curl_posts_a_ticket_batch_with_the_token_from_the_environment", () => {
    const curl = ingestCurl(SERVER, "tickets");
    const lines = curl.split("\n");

    expect(lines[0]).toBe('curl -X POST "https://kb.example.test/v1/ingest/tickets" \\');
    expect(lines[1]).toBe('  -H "Authorization: Bearer $KNOBRIDGE_INGEST_TOKEN" \\');
    expect(curl).not.toMatch(/kbi_/);
    expect(curlBody(curl)).toMatchObject({
      items: [{ op: "upsert", ticket: { external_id: "4f6c2a10-0001", status: "resolved" } }],
    });
  });

  it("test_ingest_curl_posts_a_card_to_the_cards_route", () => {
    const curl = ingestCurl(SERVER, "cards");

    expect(curl.split("\n")[0]).toBe('curl -X POST "https://kb.example.test/v1/ingest/cards" \\');
    expect(curlBody(curl)).toMatchObject({
      items: [{ op: "upsert", card: { number: "PROJ-123", type: "feature", status: "done" } }],
    });
  });
});

describe("ingestPython", () => {
  it("test_ingest_python_reads_the_token_and_posts_tickets_to_the_server", () => {
    const python = ingestPython(SERVER, "tickets");

    expect(python).toContain('TOKEN = os.environ["KNOBRIDGE_INGEST_TOKEN"]');
    expect(python).toContain('URL = "https://kb.example.test/v1/ingest/tickets"');
    expect(python).toContain('    {"op": "upsert", "ticket": {');
    expect(python).toContain('        "external_id": "4f6c2a10-0001",');
    expect(python).not.toMatch(/kbi_|true|false|null/);
  });

  it("test_ingest_python_posts_cards_with_the_card_key", () => {
    const python = ingestPython(SERVER, "cards");

    expect(python).toContain('URL = "https://kb.example.test/v1/ingest/cards"');
    expect(python).toContain('    {"op": "upsert", "card": {');
    expect(python).not.toMatch(/kbi_|true|false|null/);
  });
});

describe("parsePushSourceTab", () => {
  it("test_parse_push_source_tab_falls_back_to_the_first", () => {
    expect(parsePushSourceTab("preview")).toBe("preview");
    expect(parsePushSourceTab("modules")).toBe("integration");
    expect(parsePushSourceTab(null)).toBe("integration");
  });
});
