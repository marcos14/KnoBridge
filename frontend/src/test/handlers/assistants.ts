import { http, HttpResponse } from "msw";

import type {
  Assistant,
  AssistantChanges,
  AssistantInput,
  TicketWebhookSecret,
  TicketWebhookTest,
} from "@/lib/api/assistants";

import { makeAssistant, makeAssistants } from "../factories";
import { apiErrorResponse } from "./errors";
import { page } from "./page";

const ASSISTANTS = "*/v1/workspaces/:workspaceId/assistants";
const ASSISTANT = "*/v1/workspaces/:workspaceId/assistants/:assistantId";
const SECRET = `${ASSISTANT}/ticket-webhook/secret`;
const TEST = `${ASSISTANT}/ticket-webhook/test`;

/** POST .../ticket-webhook/secret refused with `status` and `code`. */
export function rotateWebhookSecretFails(status: number, code: string) {
  return http.post(SECRET, () => apiErrorResponse(status, code));
}

/** Stored when the request leaves `no_source_message` empty, like the backend default. */
export const DEFAULT_NO_SOURCE_MESSAGE = "Mensagem padrão de sem fonte.";

function noContent() {
  return new HttpResponse(null, { status: 204 });
}

/** GET /v1/workspaces/{id}/assistants listing `assistants` (default: Rascunho and Suporte ERP). */
export function assistantsAs(assistants: Assistant[] = makeAssistants()) {
  return http.get(ASSISTANTS, ({ request }) => page(request, assistants));
}

/** Drops the fields a PATCH sent as null, which the backend keeps as they are. */
function definedChanges(body: AssistantChanges): Partial<Assistant> {
  return Object.fromEntries(Object.entries(body).filter(([, value]) => value !== null));
}

/** What the backend stores for `no_source_message`: its default when empty or null. */
function storedNoSourceMessage(message: string | null | undefined): string {
  return message === null || message === undefined || message === ""
    ? DEFAULT_NO_SOURCE_MESSAGE
    : message;
}

/** Stored when the request omits them, like the backend defaults. */
export const DEFAULT_MIN_SIMILARITY = 0.35;

/** What the backend stores for a `POST` body: its defaults for the omitted fields. */
function storedInput(body: AssistantInput): Partial<Assistant> {
  return {
    ...body,
    collection_ids: body.collection_ids ?? [],
    min_similarity: body.min_similarity ?? DEFAULT_MIN_SIMILARITY,
    no_source_message: storedNoSourceMessage(body.no_source_message),
    ticket_webhook_url: body.ticket_webhook_url ?? null,
  };
}

/** `ticket_webhook_configured` as the backend computes it: URL and secret. */
function withWebhookState(assistant: Assistant): Assistant {
  return {
    ...assistant,
    ticket_webhook_configured:
      assistant.ticket_webhook_url !== null && assistant.ticket_webhook_secret_created_at !== null,
  };
}

/** The `kbw_` secret `POST .../ticket-webhook/secret` returns in the tests (fake). */
export const WEBHOOK_SECRET = "kbw_CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC";
/** When the store "generates" the secret. */
export const WEBHOOK_SECRET_CREATED_AT = "2026-10-12T09:00:00Z";

/** A delivery the destination accepted. */
export function makeWebhookTest(overrides: Partial<TicketWebhookTest> = {}): TicketWebhookTest {
  return {
    ok: true,
    delivery_id: "00000000-0000-4000-8000-0000000001f1",
    status: 204,
    error: null,
    ...overrides,
  };
}

interface AssistantStoreOptions {
  /** Answer of "Testar entrega" (default: accepted with 204), or a JSON error. */
  webhookTest?: TicketWebhookTest | Response;
}

/**
 * Assistants that really change: `POST` adds one (409 `assistant_name_taken` for a name in use),
 * `PATCH` applies the given fields (`ticket_webhook_url: null` turns the webhook off) and `DELETE`
 * removes it. An empty `no_source_message` stores `DEFAULT_NO_SOURCE_MESSAGE`. The webhook secret
 * is "generated" as `WEBHOOK_SECRET` and the test answers `options.webhookTest`.
 * `created`, `changes`, `deleted`, `secretRotations` and `webhookTests` keep what was asked.
 */
export function assistantStore(
  initial: Assistant[] = makeAssistants(),
  options: AssistantStoreOptions = {},
) {
  let assistants = [...initial];
  const created: AssistantInput[] = [];
  const changes: { assistantId: string; body: AssistantChanges }[] = [];
  const deleted: string[] = [];
  const secretRotations: string[] = [];
  const webhookTests: string[] = [];
  const find = (id: string) => assistants.find((item) => item.id === id);
  const replace = (updated: Assistant) => {
    assistants = assistants.map((item) => (item.id === updated.id ? updated : item));
  };
  const handlers = [
    http.post(SECRET, ({ params }) => {
      const assistant = find(String(params.assistantId));
      if (assistant === undefined) {
        return apiErrorResponse(404, "not_found");
      }
      secretRotations.push(assistant.id);
      replace(
        withWebhookState({
          ...assistant,
          ticket_webhook_secret_created_at: WEBHOOK_SECRET_CREATED_AT,
        }),
      );
      return HttpResponse.json<TicketWebhookSecret>(
        { secret: WEBHOOK_SECRET, created_at: WEBHOOK_SECRET_CREATED_AT },
        { status: 201 },
      );
    }),
    http.post(TEST, ({ params }) => {
      webhookTests.push(String(params.assistantId));
      const answer = options.webhookTest ?? makeWebhookTest();
      return answer instanceof Response ? answer : HttpResponse.json<TicketWebhookTest>(answer);
    }),
    http.get(ASSISTANTS, ({ request }) => page(request, assistants)),
    http.post(ASSISTANTS, async ({ request }) => {
      const body = (await request.json()) as AssistantInput;
      if (assistants.some((item) => item.name === body.name)) {
        return apiErrorResponse(409, "assistant_name_taken");
      }
      const assistant = makeAssistant({
        ...storedInput(body),
        id: `00000000-0000-4000-8000-${String(970 + created.length).padStart(12, "0")}`,
      });
      assistants = [...assistants, assistant].sort((a, b) => a.name.localeCompare(b.name));
      created.push(body);
      return HttpResponse.json<Assistant>(assistant, { status: 201 });
    }),
    http.patch(ASSISTANT, async ({ params, request }) => {
      const assistantId = String(params.assistantId);
      const body = (await request.json()) as AssistantChanges;
      const assistant = find(assistantId);
      if (assistant === undefined) {
        return apiErrorResponse(404, "not_found");
      }
      const updated = withWebhookState({
        ...assistant,
        ...definedChanges(body),
        no_source_message:
          body.no_source_message === undefined
            ? assistant.no_source_message
            : storedNoSourceMessage(body.no_source_message),
        ticket_webhook_url:
          body.ticket_webhook_url === undefined
            ? assistant.ticket_webhook_url
            : body.ticket_webhook_url,
      });
      replace(updated);
      changes.push({ assistantId, body });
      return HttpResponse.json<Assistant>(updated);
    }),
    http.delete(ASSISTANT, ({ params }) => {
      const assistantId = String(params.assistantId);
      if (find(assistantId) === undefined) {
        return apiErrorResponse(404, "not_found");
      }
      assistants = assistants.filter((item) => item.id !== assistantId);
      deleted.push(assistantId);
      return noContent();
    }),
  ];
  return { handlers, created, changes, deleted, secretRotations, webhookTests };
}

/** GET /v1/workspaces/{id}/assistants with the default list. */
export const assistantsOk = assistantsAs();

/** GET /v1/workspaces/{id}/assistants failing on the server (500). */
export const assistantsServerError = http.get(ASSISTANTS, () =>
  apiErrorResponse(500, "internal_error"),
);

/** POST /v1/workspaces/{id}/assistants creating the assistant (201). */
export const createAssistantOk = http.post(ASSISTANTS, async ({ request }) => {
  const body = (await request.json()) as AssistantInput;
  return HttpResponse.json<Assistant>(makeAssistant(storedInput(body)), { status: 201 });
});

/** POST /v1/workspaces/{id}/assistants refused with `status` and `code`. */
export function createAssistantFails(status: number, code: string) {
  return http.post(ASSISTANTS, () => apiErrorResponse(status, code));
}

/** PATCH /v1/workspaces/{id}/assistants/{assistant_id} answering with the default assistant. */
export const updateAssistantOk = http.patch(ASSISTANT, () =>
  HttpResponse.json<Assistant>(makeAssistant()),
);

/** PATCH /v1/workspaces/{id}/assistants/{assistant_id} refused with `status`, `code`, `details`. */
export function updateAssistantFails(status: number, code: string, details: unknown = null) {
  return http.patch(ASSISTANT, () => apiErrorResponse(status, code, details));
}

/** DELETE /v1/workspaces/{id}/assistants/{assistant_id} removing it (204). */
export const deleteAssistantOk = http.delete(ASSISTANT, noContent);

/** DELETE /v1/workspaces/{id}/assistants/{assistant_id} refused with `status` and `code`. */
export function deleteAssistantFails(status: number, code: string) {
  return http.delete(ASSISTANT, () => apiErrorResponse(status, code));
}

export const assistantsHandlers = [
  assistantsOk,
  createAssistantOk,
  updateAssistantOk,
  deleteAssistantOk,
];
