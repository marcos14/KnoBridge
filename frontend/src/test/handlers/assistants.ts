import { http, HttpResponse } from "msw";

import type { Assistant, AssistantChanges, AssistantInput } from "@/lib/api/assistants";

import { makeAssistant, makeAssistants } from "../factories";
import { apiErrorResponse } from "./errors";
import { page } from "./page";

const ASSISTANTS = "*/v1/workspaces/:workspaceId/assistants";
const ASSISTANT = "*/v1/workspaces/:workspaceId/assistants/:assistantId";

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
  };
}

/**
 * Assistants that really change: `POST` adds one (409 `assistant_name_taken` for a name in use),
 * `PATCH` applies the given fields and `DELETE` removes it. An empty `no_source_message` stores
 * `DEFAULT_NO_SOURCE_MESSAGE`. `created`, `changes` and `deleted` keep what was asked, in order.
 */
export function assistantStore(initial: Assistant[] = makeAssistants()) {
  let assistants = [...initial];
  const created: AssistantInput[] = [];
  const changes: { assistantId: string; body: AssistantChanges }[] = [];
  const deleted: string[] = [];
  const find = (id: string) => assistants.find((item) => item.id === id);
  const handlers = [
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
      const updated: Assistant = {
        ...assistant,
        ...definedChanges(body),
        no_source_message:
          body.no_source_message === undefined
            ? assistant.no_source_message
            : storedNoSourceMessage(body.no_source_message),
      };
      assistants = assistants.map((item) => (item.id === assistantId ? updated : item));
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
  return { handlers, created, changes, deleted };
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

/** PATCH /v1/workspaces/{id}/assistants/{assistant_id} refused with `status` and `code`. */
export function updateAssistantFails(status: number, code: string) {
  return http.patch(ASSISTANT, () => apiErrorResponse(status, code));
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
