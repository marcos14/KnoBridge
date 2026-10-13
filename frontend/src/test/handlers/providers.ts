import { http, HttpResponse } from "msw";

import type {
  Provider,
  ProviderChanges,
  ProviderInput,
  ProviderTestResult,
} from "@/lib/api/providers";

import { makeProvider, makeProviders } from "../factories";
import { apiErrorResponse } from "./errors";
import { listRecorder, page } from "./page";

const PROVIDERS = "*/v1/workspaces/:workspaceId/providers";
const PROVIDER = "*/v1/workspaces/:workspaceId/providers/:providerId";
const TEST = "*/v1/workspaces/:workspaceId/providers/:providerId/test";

function noContent() {
  return new HttpResponse(null, { status: 204 });
}

/** Masked key as the API shows it: the last four characters only. */
function hint(apiKey: string): string {
  return `****${apiKey.trim().slice(-4)}`;
}

/** `ok: false` test result with the provider error `code`, as the API reports it. */
export function failedTest(code: string, status: number | null = 401): ProviderTestResult {
  return {
    ok: false,
    error: { code, message: `Synthetic ${code} error.`, details: { provider: "openai", status } },
  };
}

/** GET /v1/workspaces/{id}/providers listing `providers` (default: Anthropic and OpenAI). */
export function providersAs(providers: Provider[] = makeProviders()) {
  return http.get(PROVIDERS, ({ request }) => page(request, providers));
}

interface ProviderStoreOptions {
  /** Providers an assistant uses: deleting them answers 409 `provider_in_use`. */
  inUse?: string[];
  /** Result of `POST .../test` per provider id (default: success). */
  testResults?: Record<string, ProviderTestResult>;
}

/**
 * Providers that really change: `POST` adds one (409 `provider_name_taken` for a name in use),
 * `PATCH` renames, sets or clears `base_url` and replaces the key, `DELETE` removes it. Keys only
 * come back masked. `created`, `changes`, `deleted` and `tested` keep what was asked, in order.
 */
export function providerStore(
  initial: Provider[] = makeProviders(),
  { inUse = [], testResults = {} }: ProviderStoreOptions = {},
) {
  let providers = [...initial];
  const created: ProviderInput[] = [];
  const changes: { providerId: string; body: ProviderChanges }[] = [];
  const deleted: string[] = [];
  const tested: string[] = [];
  const find = (id: string) => providers.find((item) => item.id === id);
  const nameTaken = (name: string, except?: string) =>
    providers.some((item) => item.name === name && item.id !== except);
  const handlers = [
    http.get(PROVIDERS, ({ request }) => page(request, providers)),
    http.post(PROVIDERS, async ({ request }) => {
      const body = (await request.json()) as ProviderInput;
      if (nameTaken(body.name)) {
        return apiErrorResponse(409, "provider_name_taken");
      }
      const provider = makeProvider({
        id: `00000000-0000-4000-8000-${String(950 + created.length).padStart(12, "0")}`,
        name: body.name,
        kind: body.kind,
        base_url: body.base_url ?? null,
        key_hint: hint(body.api_key),
      });
      providers = [...providers, provider].sort((a, b) => a.name.localeCompare(b.name));
      created.push(body);
      return HttpResponse.json<Provider>(provider, { status: 201 });
    }),
    http.patch(PROVIDER, async ({ params, request }) => {
      const providerId = String(params.providerId);
      const body = (await request.json()) as ProviderChanges;
      const provider = find(providerId);
      if (provider === undefined) {
        return apiErrorResponse(404, "not_found");
      }
      if (body.name != null && nameTaken(body.name, providerId)) {
        return apiErrorResponse(409, "provider_name_taken");
      }
      const updated: Provider = {
        ...provider,
        name: body.name ?? provider.name,
        base_url: "base_url" in body ? (body.base_url ?? null) : provider.base_url,
        key_hint: body.api_key == null ? provider.key_hint : hint(body.api_key),
      };
      providers = providers.map((item) => (item.id === providerId ? updated : item));
      changes.push({ providerId, body });
      return HttpResponse.json<Provider>(updated);
    }),
    http.delete(PROVIDER, ({ params }) => {
      const providerId = String(params.providerId);
      if (find(providerId) === undefined) {
        return apiErrorResponse(404, "not_found");
      }
      if (inUse.includes(providerId)) {
        return apiErrorResponse(409, "provider_in_use");
      }
      providers = providers.filter((item) => item.id !== providerId);
      deleted.push(providerId);
      return noContent();
    }),
    http.post(TEST, ({ params }) => {
      const providerId = String(params.providerId);
      tested.push(providerId);
      return HttpResponse.json<ProviderTestResult>(
        testResults[providerId] ?? { ok: true, error: null },
      );
    }),
  ];
  return { handlers, created, changes, deleted, tested };
}

/** GET of the provider list recording each query string; `query` matches the name. */
export function providersRecorder(providers: Provider[] = makeProviders()) {
  return listRecorder(PROVIDERS, providers, (item) => [item.name]);
}

/** GET /v1/workspaces/{id}/providers with the default list. */
export const providersOk = providersAs();

/** GET /v1/workspaces/{id}/providers failing on the server (500). */
export const providersServerError = http.get(PROVIDERS, () =>
  apiErrorResponse(500, "internal_error"),
);

/** POST /v1/workspaces/{id}/providers creating the provider (201). */
export const createProviderOk = http.post(PROVIDERS, async ({ request }) => {
  const body = (await request.json()) as ProviderInput;
  return HttpResponse.json<Provider>(
    makeProvider({ name: body.name, kind: body.kind, key_hint: hint(body.api_key) }),
    { status: 201 },
  );
});

/** POST /v1/workspaces/{id}/providers refused with `status` and `code`. */
export function createProviderFails(status: number, code: string) {
  return http.post(PROVIDERS, () => apiErrorResponse(status, code));
}

/** PATCH /v1/workspaces/{id}/providers/{provider_id} answering with the default provider. */
export const updateProviderOk = http.patch(PROVIDER, () =>
  HttpResponse.json<Provider>(makeProvider()),
);

/** PATCH /v1/workspaces/{id}/providers/{provider_id} refused with `status` and `code`. */
export function updateProviderFails(status: number, code: string) {
  return http.patch(PROVIDER, () => apiErrorResponse(status, code));
}

/** DELETE /v1/workspaces/{id}/providers/{provider_id} removing it (204). */
export const deleteProviderOk = http.delete(PROVIDER, noContent);

/** DELETE /v1/workspaces/{id}/providers/{provider_id} refused with `status` and `code`. */
export function deleteProviderFails(status: number, code: string) {
  return http.delete(PROVIDER, () => apiErrorResponse(status, code));
}

/** POST /v1/workspaces/{id}/providers/{provider_id}/test reporting success. */
export const testProviderOk = http.post(TEST, () =>
  HttpResponse.json<ProviderTestResult>({ ok: true, error: null }),
);

/** POST /v1/workspaces/{id}/providers/{provider_id}/test refused by the API itself. */
export function testProviderFails(status: number, code: string) {
  return http.post(TEST, () => apiErrorResponse(status, code));
}

export const providersHandlers = [
  providersOk,
  createProviderOk,
  updateProviderOk,
  deleteProviderOk,
  testProviderOk,
];
