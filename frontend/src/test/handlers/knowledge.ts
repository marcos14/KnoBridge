import { http, HttpResponse } from "msw";

import type { KnowledgeItem, KnowledgeItemPatch } from "@/lib/api/knowledge";

import { makeKnowledgeItems, makeRuleItem } from "../knowledgeFactories";
import { apiErrorResponse } from "./errors";
import { page } from "./page";

const ITEMS = "*/v1/workspaces/:workspaceId/sources/:sourceId/knowledge";
const ITEM = "*/v1/workspaces/:workspaceId/sources/:sourceId/knowledge/:itemId";
const EXPORT = "*/v1/workspaces/:workspaceId/sources/:sourceId/knowledge/export";

/** Instant the store writes when an item is reviewed. */
const STORE_NOW = "2026-10-10T12:00:00Z";

/** Bytes of a zip's local file header signature: enough to tell the body apart. */
const ZIP_BYTES = new Uint8Array([0x50, 0x4b, 0x03, 0x04]);

/** The items of `request` filtered like the API (`module`, `review_status`, `confidence`, `kind`). */
function filtered(request: Request, items: readonly KnowledgeItem[]): KnowledgeItem[] {
  const query = new URL(request.url).searchParams;
  const want = (name: string, value: string) => {
    const expected = query.get(name);
    return expected === null || expected === value;
  };
  return items.filter(
    (item) =>
      want("module", item.module_key) &&
      want("review_status", item.review_status) &&
      want("confidence", item.confidence) &&
      want("kind", item.kind),
  );
}

/**
 * `GET .../knowledge/export`: a tiny zip named like the server does, `erp-local-<module>.zip`
 * (`erp-local.zip` without module), with `filename` ASCII and `filename*` UTF-8.
 */
export function knowledgeExportOk(sourceName = "erp-local") {
  return http.get(EXPORT, ({ request }) => exportResponse(request, sourceName));
}

function exportResponse(request: Request, sourceName: string) {
  const module = new URL(request.url).searchParams.get("module");
  const name = module === null ? `${sourceName}.zip` : `${sourceName}-${module}.zip`;
  const ascii = name.replace(/[^A-Za-z0-9._-]+/g, "_");
  return new HttpResponse(ZIP_BYTES, {
    headers: {
      "Content-Type": "application/zip",
      "Content-Disposition": `attachment; filename="${ascii}"; filename*=UTF-8''${encodeURIComponent(name)}`,
    },
  });
}

/** `GET .../knowledge/export` refused with `status` and `code` (e.g. 404 `module_not_found`). */
export function knowledgeExportFails(status: number, code: string) {
  return http.get(EXPORT, () => apiErrorResponse(status, code));
}

/** `PATCH .../knowledge/{id}` refused with `status`, `code` and `details`. */
export function knowledgeReviewFails(status: number, code: string, details: unknown = null) {
  return http.patch(ITEM, () => apiErrorResponse(status, code, details));
}

/** `GET .../knowledge` failing on the server (500). */
export const knowledgeServerError = http.get(ITEMS, () => apiErrorResponse(500, "internal_error"));

/**
 * A `PATCH .../knowledge/{id}` that waits for the test: `respond(item)` answers 200 with it,
 * `fail(status, code)` with an error. To see the optimistic state before the answer, without
 * timers.
 */
export function controlledReview() {
  let settle: (response: Response) => void = () => undefined;
  const answer = new Promise<Response>((resolve) => {
    settle = resolve;
  });
  const bodies: KnowledgeItemPatch[] = [];
  const handler = http.patch(ITEM, async ({ request }) => {
    bodies.push((await request.json()) as KnowledgeItemPatch);
    return answer;
  });
  return {
    handler,
    bodies,
    respond: (item: KnowledgeItem) => {
      settle(HttpResponse.json<KnowledgeItem>(item));
    },
    fail: (status: number, code: string) => {
      settle(apiErrorResponse(status, code));
    },
  };
}

/**
 * Knowledge items that really change, with the backend's review rules: `title`/`content` go to
 * `edited` and clear `evidence_changed`; `approve` → approved and `revisado`; `discard` →
 * discarded; `reopen` → pending and `inferido`; 404 `knowledge_item_not_found` for an unknown id.
 * `changes` keeps each body; `queries` the query string of each list read; `exports` the
 * `module` of each export (`null` without).
 */
export function knowledgeStore(initial: KnowledgeItem[] = makeKnowledgeItems()) {
  let items = [...initial];
  const changes: { itemId: string; body: KnowledgeItemPatch }[] = [];
  const queries: string[] = [];
  const exports: (string | null)[] = [];

  function review(item: KnowledgeItem, body: KnowledgeItemPatch): KnowledgeItem {
    let updated: KnowledgeItem = { ...item, updated_at: STORE_NOW };
    if (body.title != null || body.content != null) {
      updated = {
        ...updated,
        edited: {
          ...(item.edited ?? {}),
          ...(body.title == null ? {} : { title: body.title }),
          ...(body.content == null ? {} : { content: body.content }),
        },
        evidence_changed: false,
      };
    }
    if (body.action === "approve") {
      updated = {
        ...updated,
        review_status: "approved",
        confidence: "revisado",
        evidence_changed: false,
      };
    } else if (body.action === "discard") {
      updated = { ...updated, review_status: "discarded" };
    } else if (body.action === "reopen") {
      updated = { ...updated, review_status: "pending", confidence: "inferido" };
    }
    return updated;
  }

  const handlers = [
    http.get(EXPORT, ({ request }) => {
      exports.push(new URL(request.url).searchParams.get("module"));
      return exportResponse(request, "erp-local");
    }),
    http.get(ITEMS, ({ request }) => {
      queries.push(new URL(request.url).searchParams.toString());
      return page(request, filtered(request, items));
    }),
    http.patch(ITEM, async ({ params, request }) => {
      const itemId = String(params.itemId);
      const body = (await request.json()) as KnowledgeItemPatch;
      const item = items.find((entry) => entry.id === itemId);
      if (item === undefined) {
        return apiErrorResponse(404, "knowledge_item_not_found");
      }
      const updated = review(item, body);
      items = items.map((entry) => (entry.id === itemId ? updated : entry));
      changes.push({ itemId, body });
      return HttpResponse.json<KnowledgeItem>(updated);
    }),
  ];

  return { handlers, changes, queries, exports };
}

/**
 * Stateless defaults: the items of "src/faturamento" filtered like the API, a review that answers
 * with the default rule and an export that downloads.
 */
export const knowledgeHandlers = [
  knowledgeExportOk(),
  http.get(ITEMS, ({ request }) => page(request, filtered(request, makeKnowledgeItems()))),
  http.patch(ITEM, () => HttpResponse.json<KnowledgeItem>(makeRuleItem())),
];
