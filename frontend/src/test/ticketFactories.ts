import type { Citation } from "@/lib/api/conversations";
import type { Source } from "@/lib/api/sources";
import type { TicketRequest, TicketRequestPreview } from "@/lib/api/ticketRequests";
import type {
  IngestToken,
  TicketPreview,
  TicketsSummary,
  TicketUploadError,
  TicketUploadReport,
} from "@/lib/api/tickets";

import { ASSISTANT_ID, CONVERSATION_ID, makeCitation, makeSource, messageId } from "./factories";

/** Synthetic data of the tickets source "suporte" (plan 0005); nothing comes from a real system. */
export const TICKETS_SOURCE_ID = "00000000-0000-4000-8000-0000000001b4";

/** The token the panel shows once after `POST .../ingest-token` (fake, same shape as the API's). */
export const INGEST_TOKEN = "kbi_ab12cd34_BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB";

/** "suporte": a tickets source in Código ERP, anonymizing, without internal notes, all statuses. */
export function makeTicketsSource(overrides: Partial<Source> = {}): Source {
  return makeSource({
    id: TICKETS_SOURCE_ID,
    name: "suporte",
    kind: "tickets",
    config: {
      include_internal_notes: false,
      anonymize: true,
      statuses: ["open", "pending", "resolved", "closed"],
    },
    include_globs: [],
    exclude_globs: [],
    document_count: 0,
    last_run: null,
    ...overrides,
  });
}

export function makeIngestToken(overrides: Partial<IngestToken> = {}): IngestToken {
  return {
    token: INGEST_TOKEN,
    token_prefix: "ab12cd34",
    created_at: "2026-10-10T12:00:00Z",
    ...overrides,
  };
}

/**
 * The summary of "suporte" before any token or ticket: zero everywhere, no token, nothing
 * received. Tests override the counts and dates they read.
 */
export function makeTicketsSummary(overrides: Partial<TicketsSummary> = {}): TicketsSummary {
  return {
    counts: { pending: 0, indexed: 0, filtered: 0, pending_delete: 0, deleted: 0 },
    failed: 0,
    last_received_at: null,
    token_prefix: null,
    token_created_at: null,
    ...overrides,
  };
}

/** A synthetic ticket in the API format, as pasted into the preview. */
export const SAMPLE_TICKET = {
  external_id: "4f6c2a10-0001",
  number: "48213",
  title: "Erro 4021 ao fechar o caixa",
  status: "resolved",
  created_at: "2026-09-30T14:02:00-03:00",
  updated_at: "2026-10-01T09:15:00-03:00",
  messages: [
    {
      role: "customer",
      author_name: "Ana Souza",
      body: "Ao fechar o caixa aparece o erro 4021. Meu telefone é (11) 98765-4321.",
      created_at: "2026-09-30T14:02:00-03:00",
    },
  ],
};

export function makeTicketPreview(overrides: Partial<TicketPreview> = {}): TicketPreview {
  return {
    title: "Erro 4021 ao fechar o caixa",
    markdown:
      "# Chamado 48213: Erro 4021 ao fechar o caixa\n\n- Status: Resolvido\n\n## Problema\n\nAo fechar o caixa aparece o erro 4021. Meu telefone é [TELEFONE].",
    markers: [
      { marker: "[TELEFONE]", count: 1 },
      { marker: "[SOLICITANTE]", count: 2 },
    ],
    anonymize: true,
    include_internal_notes: false,
    ...overrides,
  };
}

export function makeTicketUploadError(
  overrides: Partial<TicketUploadError> = {},
): TicketUploadError {
  return {
    line: 2,
    index: null,
    external_id: "A-2",
    code: "validation_error",
    message: "Synthetic validation error.",
    details: [
      { loc: ["status"], problem: "enum" },
      { loc: ["messages", 0, "created_at"], problem: "missing" },
    ],
    ...overrides,
  };
}

/**
 * Report of a `.jsonl` upload with 4 lines: 2 queued, 1 unchanged and the 3 rejections below
 * (`validation_error` on line 2, `invalid_json` on line 3, `duplicate_in_batch` on line 4).
 */
export function makeTicketUploadReport(
  overrides: Partial<TicketUploadReport> = {},
): TicketUploadReport {
  return {
    format: "jsonl",
    total: 6,
    counts: { queued: 2, unchanged: 1, stale: 0, rejected: 3 },
    errors: [
      makeTicketUploadError(),
      makeTicketUploadError({
        line: 3,
        external_id: null,
        code: "invalid_json",
        message: "Synthetic invalid JSON.",
        details: null,
      }),
      makeTicketUploadError({
        line: 4,
        external_id: "A-1",
        code: "duplicate_in_batch",
        message: "Synthetic duplicate.",
        details: { first_index: 1 },
      }),
    ],
    errors_truncated: false,
    sync: "started",
    run_id: "00000000-0000-4000-8000-0000000001c9",
    ...overrides,
  };
}

export const TICKET_REQUEST_ID = "00000000-0000-4000-8000-0000000001e1";

/** A ticket asked for answer `messageId(2)` of the default conversation, still being sent. */
export function makeTicketRequest(overrides: Partial<TicketRequest> = {}): TicketRequest {
  return {
    id: TICKET_REQUEST_ID,
    conversation_id: CONVERSATION_ID,
    message_id: messageId(2),
    assistant_id: ASSISTANT_ID,
    status: "pending",
    attempts: 0,
    external_ticket_id: null,
    external_url: null,
    error_code: null,
    created_at: "2026-10-12T13:00:00Z",
    delivered_at: null,
    ...overrides,
  };
}

/** What `POST .../ticket-requests/preview` shows: Ana's question with a generated summary. */
export function makeTicketRequestPreview(
  overrides: Partial<TicketRequestPreview> = {},
): TicketRequestPreview {
  return {
    message_id: messageId(2),
    question: "Como emito nota fiscal para cliente do exterior?",
    summary: "A usuária quer emitir nota de exportação e não achou o passo a passo.",
    summary_generated: true,
    requester: { name: "Ana Teste", email: "ana@example.test" },
    messages: [
      {
        role: "user",
        content: "Como emito nota fiscal para cliente do exterior?",
        created_at: "2026-10-12T12:59:50Z",
      },
      {
        role: "assistant",
        content: "Não encontrei isso nas fontes.",
        created_at: "2026-10-12T12:59:51Z",
      },
    ],
    ...overrides,
  };
}

/** Citation `kind: ticket` (v0.6) of ticket 48213, resolved, with its link. */
export function makeTicketCitation(overrides: Partial<Citation> = {}): Citation {
  return makeCitation({
    title: "Erro 4021 ao fechar o caixa",
    uri: "ticket:4f6c2a10-0001",
    snippet: "Finalizar a sangria do turno anterior libera o fechamento.",
    document_id: "doc-ticket-48213",
    kind: "ticket",
    path: null,
    sha: null,
    ticket_number: "48213",
    ticket_status: "resolved",
    // Midday UTC: the same calendar day in any time zone the tests may run in.
    date: "2026-10-01T12:00:00Z",
    ticket_date_kind: "resolved",
    url: "https://suporte.example.test/chamados/48213",
    ...overrides,
  });
}
