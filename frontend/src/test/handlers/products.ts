import { http, HttpResponse } from "msw";

import type {
  Product,
  ProductChanges,
  ProductInput,
  TicketWebhookSecret,
  TicketWebhookTest,
} from "@/lib/api/products";

import { makeProduct, makeProducts } from "../factories";
import { apiErrorResponse } from "./errors";
import { listRecorder, page } from "./page";

const ASSISTANTS = "*/v1/workspaces/:workspaceId/products";
const ASSISTANT = "*/v1/workspaces/:workspaceId/products/:productId";
const SECRET = `${ASSISTANT}/ticket-webhook/secret`;
const TEST = `${ASSISTANT}/ticket-webhook/test`;
const DUPLICATE = `${ASSISTANT}/duplicate`;

/** Id of the copy `POST .../duplicate` answers by default. */
export const DUPLICATED_PRODUCT_ID = "00000000-0000-4000-8000-0000000000f9";

/**
 * POST .../duplicate answering `copy` (201; default: "Suporte ERP (cópia)"), keeping the id of the
 * original and the JSON body of each request in `requests`.
 */
export function duplicateProductRecorder(
  copy: Product = makeProduct({ id: DUPLICATED_PRODUCT_ID, name: "Suporte ERP (cópia)" }),
) {
  const requests: { productId: string; body: unknown }[] = [];
  const handler = http.post(DUPLICATE, async ({ params, request }) => {
    requests.push({ productId: String(params.productId), body: await request.json() });
    return HttpResponse.json<Product>(copy, { status: 201 });
  });
  return { handler, requests };
}

/** POST .../duplicate refused with `status` and `code`. */
export function duplicateProductFails(status: number, code: string) {
  return http.post(DUPLICATE, () => apiErrorResponse(status, code));
}

/** GET of the product list recording each query string; `query` matches the name. */
export function productsRecorder(products: Product[] = makeProducts()) {
  return listRecorder(ASSISTANTS, products, (item) => [item.name]);
}

/** POST .../ticket-webhook/secret refused with `status` and `code`. */
export function rotateWebhookSecretFails(status: number, code: string) {
  return http.post(SECRET, () => apiErrorResponse(status, code));
}

/** Stored when the request leaves `no_source_message` empty, like the backend default. */
export const DEFAULT_NO_SOURCE_MESSAGE = "Mensagem padrão de sem fonte.";

function noContent() {
  return new HttpResponse(null, { status: 204 });
}

/** GET /v1/workspaces/{id}/products listing `products` (default: Rascunho and Suporte ERP). */
export function productsAs(products: Product[] = makeProducts()) {
  return http.get(ASSISTANTS, ({ request }) => page(request, products));
}

/** Drops the fields a PATCH sent as null, which the backend keeps as they are. */
function definedChanges(body: ProductChanges): Partial<Product> {
  return Object.fromEntries(Object.entries(body).filter(([, value]) => value !== null));
}

/** What the backend stores for `no_source_message`: its default when empty or null. */
function storedNoSourceMessage(message: string | null | undefined): string {
  return message === null || message === undefined || message === ""
    ? DEFAULT_NO_SOURCE_MESSAGE
    : message;
}

/** The floor of `text-embedding-3-small` in the backend's table per embedding model. */
export const MODEL_MIN_SIMILARITY = 0.35;

/**
 * `effective_min_similarity` as the backend computes it for the models in `effective`: the
 * product's own floor, or the model's default when `min_similarity` is `null`.
 */
function effectiveFloors(
  effective: Product["effective_min_similarity"],
  minSimilarity: number | null,
): Product["effective_min_similarity"] {
  return effective.map((item) =>
    minSimilarity === null
      ? { ...item, value: MODEL_MIN_SIMILARITY, source: "model" }
      : { ...item, value: minSimilarity, source: "product" },
  );
}

/** What the backend stores for a `POST` body: its defaults for the omitted fields. */
function storedInput(body: ProductInput): Partial<Product> {
  const minSimilarity = body.min_similarity ?? null;
  return {
    ...body,
    collection_ids: body.collection_ids ?? [],
    min_similarity: minSimilarity,
    effective_min_similarity: effectiveFloors(
      makeProduct().effective_min_similarity,
      minSimilarity,
    ),
    no_source_message: storedNoSourceMessage(body.no_source_message),
    ticket_webhook_url: body.ticket_webhook_url ?? null,
  };
}

/** `ticket_webhook_configured` as the backend computes it: URL and secret. */
function withWebhookState(product: Product): Product {
  return {
    ...product,
    ticket_webhook_configured:
      product.ticket_webhook_url !== null && product.ticket_webhook_secret_created_at !== null,
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

interface ProductStoreOptions {
  /** Answer of "Testar entrega" (default: accepted with 204), or a JSON error. */
  webhookTest?: TicketWebhookTest | Response;
}

/**
 * Products that really change: `POST` adds one (409 `assistant_name_taken` for a name in use),
 * `PATCH` applies the given fields (`ticket_webhook_url: null` turns the webhook off) and `DELETE`
 * removes it. An empty `no_source_message` stores `DEFAULT_NO_SOURCE_MESSAGE`. The webhook secret
 * is "generated" as `WEBHOOK_SECRET` and the test answers `options.webhookTest`.
 * `created`, `changes`, `deleted`, `secretRotations` and `webhookTests` keep what was asked.
 */
export function productStore(
  initial: Product[] = makeProducts(),
  options: ProductStoreOptions = {},
) {
  let products = [...initial];
  const created: ProductInput[] = [];
  const changes: { productId: string; body: ProductChanges }[] = [];
  const deleted: string[] = [];
  const secretRotations: string[] = [];
  const webhookTests: string[] = [];
  const find = (id: string) => products.find((item) => item.id === id);
  const replace = (updated: Product) => {
    products = products.map((item) => (item.id === updated.id ? updated : item));
  };
  const handlers = [
    http.post(SECRET, ({ params }) => {
      const product = find(String(params.productId));
      if (product === undefined) {
        return apiErrorResponse(404, "not_found");
      }
      secretRotations.push(product.id);
      replace(
        withWebhookState({
          ...product,
          ticket_webhook_secret_created_at: WEBHOOK_SECRET_CREATED_AT,
        }),
      );
      return HttpResponse.json<TicketWebhookSecret>(
        { secret: WEBHOOK_SECRET, created_at: WEBHOOK_SECRET_CREATED_AT },
        { status: 201 },
      );
    }),
    http.post(TEST, ({ params }) => {
      webhookTests.push(String(params.productId));
      const answer = options.webhookTest ?? makeWebhookTest();
      return answer instanceof Response ? answer : HttpResponse.json<TicketWebhookTest>(answer);
    }),
    http.get(ASSISTANTS, ({ request }) => page(request, products)),
    http.post(ASSISTANTS, async ({ request }) => {
      const body = (await request.json()) as ProductInput;
      if (products.some((item) => item.name === body.name)) {
        return apiErrorResponse(409, "product_name_taken");
      }
      const product = makeProduct({
        ...storedInput(body),
        id: `00000000-0000-4000-8000-${String(970 + created.length).padStart(12, "0")}`,
      });
      products = [...products, product].sort((a, b) => a.name.localeCompare(b.name));
      created.push(body);
      return HttpResponse.json<Product>(product, { status: 201 });
    }),
    http.patch(ASSISTANT, async ({ params, request }) => {
      const productId = String(params.productId);
      const body = (await request.json()) as ProductChanges;
      const product = find(productId);
      if (product === undefined) {
        return apiErrorResponse(404, "not_found");
      }
      // `min_similarity: null` goes back to the model's default; omitted, it stays.
      const minSimilarity =
        body.min_similarity === undefined ? product.min_similarity : body.min_similarity;
      const updated = withWebhookState({
        ...product,
        ...definedChanges(body),
        min_similarity: minSimilarity,
        effective_min_similarity: effectiveFloors(product.effective_min_similarity, minSimilarity),
        no_source_message:
          body.no_source_message === undefined
            ? product.no_source_message
            : storedNoSourceMessage(body.no_source_message),
        ticket_webhook_url:
          body.ticket_webhook_url === undefined
            ? product.ticket_webhook_url
            : body.ticket_webhook_url,
      });
      replace(updated);
      changes.push({ productId, body });
      return HttpResponse.json<Product>(updated);
    }),
    http.delete(ASSISTANT, ({ params }) => {
      const productId = String(params.productId);
      if (find(productId) === undefined) {
        return apiErrorResponse(404, "not_found");
      }
      products = products.filter((item) => item.id !== productId);
      deleted.push(productId);
      return noContent();
    }),
  ];
  return { handlers, created, changes, deleted, secretRotations, webhookTests };
}

/** GET /v1/workspaces/{id}/products with the default list. */
export const productsOk = productsAs();

/** GET /v1/workspaces/{id}/products failing on the server (500). */
export const productsServerError = http.get(ASSISTANTS, () =>
  apiErrorResponse(500, "internal_error"),
);

/** POST /v1/workspaces/{id}/products creating the product (201). */
export const createProductOk = http.post(ASSISTANTS, async ({ request }) => {
  const body = (await request.json()) as ProductInput;
  return HttpResponse.json<Product>(makeProduct(storedInput(body)), { status: 201 });
});

/** POST /v1/workspaces/{id}/products refused with `status` and `code`. */
export function createProductFails(status: number, code: string) {
  return http.post(ASSISTANTS, () => apiErrorResponse(status, code));
}

/** PATCH /v1/workspaces/{id}/products/{product_id} answering with the default product. */
export const updateProductOk = http.patch(ASSISTANT, () =>
  HttpResponse.json<Product>(makeProduct()),
);

/** PATCH /v1/workspaces/{id}/products/{product_id} refused with `status`, `code`, `details`. */
export function updateProductFails(status: number, code: string, details: unknown = null) {
  return http.patch(ASSISTANT, () => apiErrorResponse(status, code, details));
}

/** DELETE /v1/workspaces/{id}/products/{product_id} removing it (204). */
export const deleteProductOk = http.delete(ASSISTANT, noContent);

/** DELETE /v1/workspaces/{id}/products/{product_id} refused with `status` and `code`. */
export function deleteProductFails(status: number, code: string) {
  return http.delete(ASSISTANT, () => apiErrorResponse(status, code));
}

export const productsHandlers = [
  productsOk,
  createProductOk,
  updateProductOk,
  deleteProductOk,
  duplicateProductRecorder().handler,
];
