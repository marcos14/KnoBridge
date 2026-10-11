import { http } from "msw";

import type { Source } from "@/lib/api/sources";

import { makeSource } from "../factories";
import { apiErrorResponse } from "./errors";
import { page } from "./page";

const SOURCES = "*/v1/workspaces/:workspaceId/sources";

/**
 * GET /v1/workspaces/{id}/sources listing `sources` (default: erp-core in Código ERP), filtered by
 * `collection_id` like the API.
 */
export function sourcesAs(sources: Source[] = [makeSource()]) {
  return http.get(SOURCES, ({ request }) => {
    const collectionId = new URL(request.url).searchParams.get("collection_id");
    return page(
      request,
      collectionId === null ? sources : sources.filter((s) => s.collection_id === collectionId),
    );
  });
}

/** GET /v1/workspaces/{id}/sources with the default list. */
export const sourcesOk = sourcesAs();

/** GET /v1/workspaces/{id}/sources failing on the server (500). */
export const sourcesServerError = http.get(SOURCES, () => apiErrorResponse(500, "internal_error"));

export const sourcesHandlers = [sourcesOk];
