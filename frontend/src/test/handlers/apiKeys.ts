import { http, HttpResponse } from "msw";

import type { ApiKey, ApiKeyChanges, ApiKeyCreated, ApiKeyInput } from "@/lib/api/apiKeys";

import { API_KEY_SECRET, makeApiKey, makeApiKeys } from "../apiKeyFactories";
import { makeProducts } from "../factories";
import { apiErrorResponse } from "./errors";
import { page } from "./page";

const API_KEYS = "*/v1/workspaces/:workspaceId/api-keys";
const API_KEY = "*/v1/workspaces/:workspaceId/api-keys/:apiKeyId";
const REVOKE = "*/v1/workspaces/:workspaceId/api-keys/:apiKeyId/revoke";

/** Mutations of a key, for `apiKeyActionFails`. */
export type ApiKeyAction = "create" | "update" | "revoke";

const ACTION_HANDLERS = {
  create: [http.post, API_KEYS],
  update: [http.patch, API_KEY],
  revoke: [http.post, REVOKE],
} as const;

/** Instant the store writes in `revoked_at`. */
const REVOKED_AT = "2026-10-10T12:00:00Z";

/** GET /v1/workspaces/{id}/api-keys listing `apiKeys` (default: antiga, integracao-erp, portal-cliente). */
export function apiKeysAs(apiKeys: ApiKey[] = makeApiKeys()) {
  return http.get(API_KEYS, ({ request }) => page(request, apiKeys));
}

/** GET /v1/workspaces/{id}/api-keys failing on the server (500). */
export const apiKeysServerError = http.get(API_KEYS, () => apiErrorResponse(500, "internal_error"));

/** A key mutation (`action`) refused with `status` and `code`. */
export function apiKeyActionFails(action: ApiKeyAction, status: number, code: string) {
  const [method, path] = ACTION_HANDLERS[action];
  return method(path, () => apiErrorResponse(status, code));
}

/**
 * Keys that really change, with the backend's rules: `POST` adds one and returns
 * `API_KEY_SECRET` (409 `api_key_name_taken`, 422 `api_key_product_invalid` for an id that is
 * not one of `assistantIds`), `PATCH` changes name and scope (409 `api_key_revoked` on a revoked
 * key; empty body 422), revoke is idempotent. `created`, `changes` and `revoked` keep what was
 * asked.
 */
export function apiKeyStore(
  initial: ApiKey[] = makeApiKeys(),
  assistantIds: string[] = makeProducts().map(({ id }) => id),
) {
  let apiKeys = [...initial];
  const created: ApiKeyInput[] = [];
  const changes: { apiKeyId: string; body: ApiKeyChanges }[] = [];
  const revoked: string[] = [];
  const find = (id: string) => apiKeys.find((item) => item.id === id);
  const invalidScope = (ids: string[] | null | undefined) =>
    (ids ?? []).some((id) => !assistantIds.includes(id));
  const replace = (updated: ApiKey) => {
    apiKeys = apiKeys.map((item) => (item.id === updated.id ? updated : item));
  };
  const handlers = [
    http.get(API_KEYS, ({ request }) => page(request, apiKeys)),
    http.post(API_KEYS, async ({ request }) => {
      const body = (await request.json()) as ApiKeyInput;
      if (apiKeys.some((item) => item.name === body.name)) {
        return apiErrorResponse(409, "api_key_name_taken");
      }
      if (invalidScope(body.product_ids)) {
        return apiErrorResponse(422, "api_key_product_invalid");
      }
      const apiKey = makeApiKey({
        id: `00000000-0000-4000-8000-${String(990 + created.length).padStart(12, "0")}`,
        name: body.name,
        key_prefix: "ab12cd34",
        product_ids: body.product_ids ?? null,
        max_level: body.max_level,
        created_at: REVOKED_AT,
        last_used_at: null,
      });
      apiKeys = [...apiKeys, apiKey].sort((a, b) => a.name.localeCompare(b.name));
      created.push(body);
      return HttpResponse.json<ApiKeyCreated>(
        { api_key: apiKey, key: API_KEY_SECRET },
        { status: 201 },
      );
    }),
    http.patch(API_KEY, async ({ params, request }) => {
      const apiKeyId = String(params.apiKeyId);
      const body = (await request.json()) as ApiKeyChanges;
      const apiKey = find(apiKeyId);
      if (apiKey === undefined) {
        return apiErrorResponse(404, "not_found");
      }
      if (Object.keys(body).length === 0) {
        return apiErrorResponse(422, "validation_error");
      }
      if (apiKey.revoked_at !== null) {
        return apiErrorResponse(409, "api_key_revoked");
      }
      if (apiKeys.some((item) => item.id !== apiKeyId && item.name === body.name)) {
        return apiErrorResponse(409, "api_key_name_taken");
      }
      if (invalidScope(body.product_ids)) {
        return apiErrorResponse(422, "api_key_product_invalid");
      }
      const updated: ApiKey = {
        ...apiKey,
        name: body.name ?? apiKey.name,
        product_ids: "product_ids" in body ? (body.product_ids ?? null) : apiKey.product_ids,
      };
      replace(updated);
      changes.push({ apiKeyId, body });
      return HttpResponse.json<ApiKey>(updated);
    }),
    http.post(REVOKE, ({ params }) => {
      const apiKeyId = String(params.apiKeyId);
      const apiKey = find(apiKeyId);
      if (apiKey === undefined) {
        return apiErrorResponse(404, "not_found");
      }
      const updated: ApiKey = { ...apiKey, revoked_at: apiKey.revoked_at ?? REVOKED_AT };
      replace(updated);
      revoked.push(apiKeyId);
      return HttpResponse.json<ApiKey>(updated);
    }),
  ];
  return { handlers, created, changes, revoked };
}

/** Stateless defaults: the default list, and mutations that work. */
export const apiKeysHandlers = [
  apiKeysAs(),
  http.post(API_KEYS, () =>
    HttpResponse.json<ApiKeyCreated>(
      { api_key: makeApiKey(), key: API_KEY_SECRET },
      { status: 201 },
    ),
  ),
  http.patch(API_KEY, () => HttpResponse.json<ApiKey>(makeApiKey())),
  http.post(REVOKE, () => HttpResponse.json<ApiKey>(makeApiKey({ revoked_at: REVOKED_AT }))),
];
