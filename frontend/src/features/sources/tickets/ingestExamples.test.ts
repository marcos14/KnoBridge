import { describe, expect, it } from "vitest";

import { ticketIngestCurl, ticketIngestPython } from "./ingestExamples";
import { parseTicketsSourceTab } from "./tabs";

const SERVER = "https://kb.example.test/";

describe("ticketIngestCurl", () => {
  it("test_ticket_ingest_curl_posts_a_batch_with_the_token_from_the_environment", () => {
    const curl = ticketIngestCurl(SERVER);
    const lines = curl.split("\n");

    expect(lines[0]).toBe('curl -X POST "https://kb.example.test/v1/ingest/tickets" \\');
    expect(lines[1]).toBe('  -H "Authorization: Bearer $KNOBRIDGE_INGEST_TOKEN" \\');
    expect(curl).not.toMatch(/kbi_/);
    // The body between the single quotes is the API's JSON.
    const body = /-d '(?<body>[\s\S]+)'$/.exec(curl)?.groups?.body ?? "";
    expect(JSON.parse(body)).toMatchObject({
      items: [{ op: "upsert", ticket: { external_id: "4f6c2a10-0001", status: "resolved" } }],
    });
  });
});

describe("ticketIngestPython", () => {
  it("test_ticket_ingest_python_reads_the_token_and_posts_to_the_server", () => {
    const python = ticketIngestPython(SERVER);

    expect(python).toContain('TOKEN = os.environ["KNOBRIDGE_INGEST_TOKEN"]');
    expect(python).toContain('URL = "https://kb.example.test/v1/ingest/tickets"');
    expect(python).toContain('    {"op": "upsert", "ticket": {');
    expect(python).toContain('        "external_id": "4f6c2a10-0001",');
    expect(python).not.toMatch(/kbi_|true|false|null/);
  });
});

describe("parseTicketsSourceTab", () => {
  it("test_parse_tickets_source_tab_falls_back_to_the_first", () => {
    expect(parseTicketsSourceTab("preview")).toBe("preview");
    expect(parseTicketsSourceTab("modules")).toBe("integration");
    expect(parseTicketsSourceTab(null)).toBe("integration");
  });
});
