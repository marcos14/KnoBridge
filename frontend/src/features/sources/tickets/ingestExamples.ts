/**
 * Copyable examples of `POST /v1/ingest/tickets` (`docs/specs/chamados.md`, "Envio pela API").
 * The token is never in them: they read it from this environment variable, so it stays out of
 * the shell history and of the code.
 */
export const INGEST_TOKEN_VARIABLE = "KNOBRIDGE_INGEST_TOKEN";

/**
 * A synthetic ticket for the examples. No `true`/`false`/`null` and no single quote, so the same
 * JSON is a Python literal and fits in the single-quoted `curl -d`.
 */
const EXAMPLE_TICKET = {
  external_id: "4f6c2a10-0001",
  number: "48213",
  title: "Erro 4021 ao fechar o caixa",
  status: "resolved",
  created_at: "2026-09-30T14:02:00-03:00",
  updated_at: "2026-10-01T09:15:00-03:00",
  resolved_at: "2026-10-01T09:10:00-03:00",
  messages: [
    {
      role: "customer",
      body: "Ao fechar o caixa aparece o erro 4021.",
      created_at: "2026-09-30T14:02:00-03:00",
    },
  ],
  resolution: { body: "Finalize a sangria do turno anterior e feche o caixa de novo." },
};

function ingestUrl(serverUrl: string): string {
  return `${serverUrl.replace(/\/+$/, "")}/v1/ingest/tickets`;
}

/** `curl` sending one ticket, with the token from `$KNOBRIDGE_INGEST_TOKEN`. */
export function ticketIngestCurl(serverUrl: string): string {
  const body = JSON.stringify({ items: [{ op: "upsert", ticket: EXAMPLE_TICKET }] }, null, 2);
  return [
    `curl -X POST "${ingestUrl(serverUrl)}" \\`,
    `  -H "Authorization: Bearer $${INGEST_TOKEN_VARIABLE}" \\`,
    `  -H "Content-Type: application/json" \\`,
    `  -d '${body}'`,
  ].join("\n");
}

/** Python (standard library only) sending a batch of tickets and printing the result. */
export function ticketIngestPython(serverUrl: string): string {
  const ticket = JSON.stringify(EXAMPLE_TICKET, null, 4)
    .split("\n")
    .map((line, index) => (index === 0 ? line : `    ${line}`))
    .join("\n");
  return [
    "import json",
    "import os",
    "import urllib.request",
    "",
    `TOKEN = os.environ["${INGEST_TOKEN_VARIABLE}"]`,
    `URL = "${ingestUrl(serverUrl)}"`,
    "",
    "# Up to 100 items per request; repeat a batch safely after a network error, 500 or 503.",
    "items = [",
    `    {"op": "upsert", "ticket": ${ticket}},`,
    "]",
    "",
    "request = urllib.request.Request(",
    "    URL,",
    '    data=json.dumps({"items": items}).encode("utf-8"),',
    '    headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},',
    '    method="POST",',
    ")",
    "with urllib.request.urlopen(request) as response:",
    "    result = json.load(response)",
    'print(result["counts"], result["sync"])',
  ].join("\n");
}
