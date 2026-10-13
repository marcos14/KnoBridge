import type { PushSourceKind } from "@/lib/api/tickets";

/**
 * Copyable examples of `POST /v1/ingest/tickets` and `POST /v1/ingest/cards`
 * (`docs/specs/chamados.md`, "Envio pela API"; `docs/specs/cards.md`). The token is never in them:
 * they read it from this environment variable, so it stays out of the shell history and of the
 * code.
 */
export const INGEST_TOKEN_VARIABLE = "KNOBRIDGE_INGEST_TOKEN";

/**
 * Synthetic items for the examples. No `true`/`false`/`null` and no single quote, so the same JSON
 * is a Python literal and fits in the single-quoted `curl -d`.
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

const EXAMPLE_CARD = {
  external_id: "10482",
  number: "PROJ-123",
  title: "Permitir nota fiscal de exportação",
  type: "feature",
  status: "done",
  description: { body: "Emitir NF-e de exportação com o CFOP 7101.", body_format: "markdown" },
  acceptance_criteria: { body: "A nota sai com o país de destino e o código de exportação." },
  release: "12.5",
  links: [{ kind: "ticket", target: "48213", relation: "originado por" }],
  created_at: "2026-09-01T10:00:00-03:00",
  updated_at: "2026-10-01T18:30:00-03:00",
  done_at: "2026-10-01T18:30:00-03:00",
};

/** The item key and the example of each kind (`ticket` or `card` in an `upsert` item). */
const EXAMPLES: Record<PushSourceKind, { key: string; item: object }> = {
  tickets: { key: "ticket", item: EXAMPLE_TICKET },
  cards: { key: "card", item: EXAMPLE_CARD },
};

function ingestUrl(serverUrl: string, kind: PushSourceKind): string {
  return `${serverUrl.replace(/\/+$/, "")}/v1/ingest/${kind}`;
}

/** `curl` sending one item of `kind`, with the token from `$KNOBRIDGE_INGEST_TOKEN`. */
export function ingestCurl(serverUrl: string, kind: PushSourceKind): string {
  const { key, item } = EXAMPLES[kind];
  const body = JSON.stringify({ items: [{ op: "upsert", [key]: item }] }, null, 2);
  return [
    `curl -X POST "${ingestUrl(serverUrl, kind)}" \\`,
    `  -H "Authorization: Bearer $${INGEST_TOKEN_VARIABLE}" \\`,
    `  -H "Content-Type: application/json" \\`,
    `  -d '${body}'`,
  ].join("\n");
}

/** Python (standard library only) sending a batch of `kind` and printing the result. */
export function ingestPython(serverUrl: string, kind: PushSourceKind): string {
  const { key, item } = EXAMPLES[kind];
  const literal = JSON.stringify(item, null, 4)
    .split("\n")
    .map((line, index) => (index === 0 ? line : `    ${line}`))
    .join("\n");
  return [
    "import json",
    "import os",
    "import urllib.request",
    "",
    `TOKEN = os.environ["${INGEST_TOKEN_VARIABLE}"]`,
    `URL = "${ingestUrl(serverUrl, kind)}"`,
    "",
    "# Up to 100 items per request; repeat a batch safely after a network error, 500 or 503.",
    "items = [",
    `    {"op": "upsert", "${key}": ${literal}},`,
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
