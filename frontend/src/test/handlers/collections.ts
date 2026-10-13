import { http, HttpResponse } from "msw";

import type {
  Collection,
  CollectionChanges,
  CollectionInput,
  CollectionSync,
  SearchRequest,
  SearchResult,
} from "@/lib/api/collections";

import { makeCollection, makeCollections, makeSearchResults } from "../factories";
import { apiErrorResponse } from "./errors";
import { listRecorder, page } from "./page";

const COLLECTIONS = "*/v1/workspaces/:workspaceId/collections";
const COLLECTION = "*/v1/workspaces/:workspaceId/collections/:collectionId";
const SEARCH = "*/v1/workspaces/:workspaceId/collections/:collectionId/search";
const SYNC_ALL = "*/v1/workspaces/:workspaceId/collections/:collectionId/sync";

/**
 * POST .../collections/{id}/sync answering `result` (202; default: nothing started or skipped),
 * keeping the collection ids in `synced`.
 */
export function collectionSyncAs(result: CollectionSync = { started: [], skipped: [] }) {
  const synced: string[] = [];
  const handler = http.post(SYNC_ALL, ({ params }) => {
    synced.push(String(params.collectionId));
    return HttpResponse.json<CollectionSync>(result, { status: 202 });
  });
  return { handler, synced };
}

/** POST .../collections/{id}/sync refused with `status` and `code` (503 `sync_unavailable`). */
export function collectionSyncFails(status: number, code: string) {
  return http.post(SYNC_ALL, () => apiErrorResponse(status, code));
}

/** GET of the collection list recording each query string; `query` matches name or description. */
export function collectionsRecorder(collections: Collection[] = makeCollections()) {
  return listRecorder(COLLECTIONS, collections, (item) => [item.name, item.description]);
}

function noContent() {
  return new HttpResponse(null, { status: 204 });
}

/** GET list and GET one over `collections` (unknown id: 404 `not_found`). */
function readHandlers(collections: () => readonly Collection[]) {
  return [
    http.get(COLLECTIONS, ({ request }) => page(request, collections())),
    http.get(COLLECTION, ({ params }) => {
      const found = collections().find((item) => item.id === params.collectionId);
      return found === undefined
        ? apiErrorResponse(404, "not_found")
        : HttpResponse.json<Collection>(found);
    }),
  ];
}

/** GET list and detail over `collections` (default: Código ERP and Manuais). */
export function collectionsAs(collections: Collection[] = makeCollections()) {
  return readHandlers(() => collections);
}

/** Whether a `PATCH` asks to change provider or model, which the backend locks with documents. */
function changesEmbedding(collection: Collection, body: CollectionChanges): boolean {
  return (
    (body.provider_id != null && body.provider_id !== collection.provider_id) ||
    (body.embedding_model != null && body.embedding_model !== collection.embedding_model)
  );
}

/**
 * Collections that really change, with the backend's rules: `POST` adds one (409
 * `collection_name_taken`), `PATCH` applies the given fields (409 `collection_embedding_locked`
 * when it changes provider or model of a collection with documents) and `DELETE` removes it (409
 * `collection_in_use` while it has sources). `created`, `changes` and `deleted` keep what was asked.
 */
export function collectionStore(initial: Collection[] = makeCollections()) {
  let collections = [...initial];
  const created: CollectionInput[] = [];
  const changes: { collectionId: string; body: CollectionChanges }[] = [];
  const deleted: string[] = [];
  const nameTaken = (name: string, except?: string) =>
    collections.some((item) => item.name === name && item.id !== except);
  const handlers = [
    ...readHandlers(() => collections),
    http.post(COLLECTIONS, async ({ request }) => {
      const body = (await request.json()) as CollectionInput;
      if (nameTaken(body.name)) {
        return apiErrorResponse(409, "collection_name_taken");
      }
      const collection = makeCollection({
        ...body,
        id: `00000000-0000-4000-8000-${String(990 + created.length).padStart(12, "0")}`,
        source_count: 0,
        document_count: 0,
        chunk_count: 0,
      });
      collections = [...collections, collection].sort((a, b) => a.name.localeCompare(b.name));
      created.push(body);
      return HttpResponse.json<Collection>(collection, { status: 201 });
    }),
    http.patch(COLLECTION, async ({ params, request }) => {
      const collectionId = String(params.collectionId);
      const body = (await request.json()) as CollectionChanges;
      const collection = collections.find((item) => item.id === collectionId);
      if (collection === undefined) {
        return apiErrorResponse(404, "not_found");
      }
      if (body.name != null && nameTaken(body.name, collectionId)) {
        return apiErrorResponse(409, "collection_name_taken");
      }
      if (collection.document_count > 0 && changesEmbedding(collection, body)) {
        return apiErrorResponse(409, "collection_embedding_locked");
      }
      const updated: Collection = {
        ...collection,
        name: body.name ?? collection.name,
        description: body.description ?? collection.description,
        provider_id: body.provider_id ?? collection.provider_id,
        embedding_model: body.embedding_model ?? collection.embedding_model,
      };
      collections = collections.map((item) => (item.id === collectionId ? updated : item));
      changes.push({ collectionId, body });
      return HttpResponse.json<Collection>(updated);
    }),
    http.delete(COLLECTION, ({ params }) => {
      const collectionId = String(params.collectionId);
      const collection = collections.find((item) => item.id === collectionId);
      if (collection === undefined) {
        return apiErrorResponse(404, "not_found");
      }
      if (collection.source_count > 0) {
        return apiErrorResponse(409, "collection_in_use");
      }
      collections = collections.filter((item) => item.id !== collectionId);
      deleted.push(collectionId);
      return noContent();
    }),
  ];
  return { handlers, created, changes, deleted };
}

/** GET of the list failing on the server (500). */
export const collectionsServerError = http.get(COLLECTIONS, () =>
  apiErrorResponse(500, "internal_error"),
);

/** GET of one collection failing on the server (500). */
export const collectionServerError = http.get(COLLECTION, () =>
  apiErrorResponse(500, "internal_error"),
);

/** POST /v1/workspaces/{id}/collections creating the collection (201, no documents yet). */
export const createCollectionOk = http.post(COLLECTIONS, async ({ request }) => {
  const body = (await request.json()) as CollectionInput;
  return HttpResponse.json<Collection>(
    makeCollection({ ...body, source_count: 0, document_count: 0, chunk_count: 0 }),
    { status: 201 },
  );
});

/** POST /v1/workspaces/{id}/collections refused with `status` and `code`. */
export function createCollectionFails(status: number, code: string) {
  return http.post(COLLECTIONS, () => apiErrorResponse(status, code));
}

/** PATCH answering with the default collection. */
export const updateCollectionOk = http.patch(COLLECTION, () =>
  HttpResponse.json<Collection>(makeCollection()),
);

/** PATCH refused with `status` and `code`. */
export function updateCollectionFails(status: number, code: string) {
  return http.patch(COLLECTION, () => apiErrorResponse(status, code));
}

/** DELETE removing it (204). */
export const deleteCollectionOk = http.delete(COLLECTION, noContent);

/** DELETE refused with `status` and `code`. */
export function deleteCollectionFails(status: number, code: string) {
  return http.delete(COLLECTION, () => apiErrorResponse(status, code));
}

/**
 * POST .../search answering with `results` (default: a code chunk and a commit); `bodies` keeps
 * each request body, to assert what the screen sent.
 */
export function searchRecorder(results: SearchResult[] = makeSearchResults()) {
  const bodies: SearchRequest[] = [];
  const handler = http.post(SEARCH, async ({ request }) => {
    bodies.push((await request.json()) as SearchRequest);
    return HttpResponse.json({ results });
  });
  return { handler, bodies };
}

/** POST .../search refused with `status` and `code` (e.g. a provider failure). */
export function searchFails(status: number, code: string) {
  return http.post(SEARCH, () => apiErrorResponse(status, code));
}

export const collectionsHandlers = [
  ...collectionsAs(),
  createCollectionOk,
  updateCollectionOk,
  deleteCollectionOk,
  searchRecorder().handler,
  collectionSyncAs().handler,
];
