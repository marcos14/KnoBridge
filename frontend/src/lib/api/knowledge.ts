import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { attachmentFilename, saveBlob } from "@/lib/download";

import { apiClient, unwrap } from "./client";
import { fetchAllPages } from "./pages";
import type { components } from "./schema.gen";

export type KnowledgeItem = components["schemas"]["KnowledgeItemOut"];
export type KnowledgeEvidence = components["schemas"]["KnowledgeEvidenceOut"];
export type KnowledgeItemPatch = components["schemas"]["KnowledgeItemPatch"];
export type KnowledgeReviewStatus = components["schemas"]["KnowledgeReviewStatus"];
export type KnowledgeConfidence = components["schemas"]["KnowledgeConfidence"];
export type ReviewAction = components["schemas"]["ReviewAction"];
export type RuleContent = components["schemas"]["RuleContent"];
export type ModuleContent = components["schemas"]["ModuleContent"];

/** Prefix of every knowledge query of a source (the harness key of the workspace). */
function knowledgeRootKey(workspaceId: string, sourceId: string) {
  return ["api", "workspaces", workspaceId, "harness", "sources", sourceId, "knowledge"] as const;
}

export function knowledgeItemsQueryKey(workspaceId: string, sourceId: string, module: string) {
  return [...knowledgeRootKey(workspaceId, sourceId), module] as const;
}

/**
 * Every item of one module of a runner source (any member), discarded ones included, by key. A
 * result carries at most 31 items, so the screen filters status and confidence in the browser;
 * one cache entry per module keeps the optimistic review simple. Off while no module is chosen.
 */
export function useKnowledgeItems(workspaceId: string, sourceId: string, module: string | null) {
  return useQuery({
    queryKey: knowledgeItemsQueryKey(workspaceId, sourceId, module ?? ""),
    queryFn: ({ signal }) =>
      fetchAllPages(async (page) =>
        unwrap(
          await apiClient.GET("/v1/workspaces/{workspace_id}/sources/{source_id}/knowledge", {
            params: {
              path: { workspace_id: workspaceId, source_id: sourceId },
              query: { ...page, module },
            },
            signal,
          }),
        ),
      ),
    enabled: module !== null,
  });
}

/**
 * The item as the server will answer a review (`docs/specs/harness.md`, "Revisão e exportação"):
 * `title`/`content` go to `edited` and clear `evidence_changed`; `approve` → approved and
 * `revisado`; `discard` → discarded; `reopen` → pending and `inferido`.
 */
export function reviewedItem(item: KnowledgeItem, patch: KnowledgeItemPatch): KnowledgeItem {
  const next: KnowledgeItem = { ...item };
  const title = patch.title ?? undefined;
  const content = patch.content ?? undefined;
  if (title !== undefined || content !== undefined) {
    next.edited = {
      ...(item.edited ?? {}),
      ...(title === undefined ? {} : { title }),
      ...(content === undefined ? {} : { content }),
    };
    next.evidence_changed = false;
  }
  switch (patch.action) {
    case "approve":
      return {
        ...next,
        review_status: "approved",
        confidence: "revisado",
        evidence_changed: false,
      };
    case "discard":
      return { ...next, review_status: "discarded" };
    case "reopen":
      return { ...next, review_status: "pending", confidence: "inferido" };
    default:
      return next;
  }
}

export interface KnowledgeReview {
  item: KnowledgeItem;
  patch: KnowledgeItemPatch;
}

function replaceItem(items: KnowledgeItem[] | undefined, item: KnowledgeItem) {
  return items?.map((current) => (current.id === item.id ? item : current));
}

/**
 * `PATCH .../knowledge/{item_id}` (editor): edit, approve, discard or reopen. Optimistic: the
 * module's list shows the predicted item at once and goes back to the previous one if the server
 * refuses (422 `knowledge_content_invalid`, 404 `knowledge_item_not_found`); the answer replaces
 * the prediction.
 */
export function useReviewKnowledgeItem(workspaceId: string, sourceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ item, patch }: KnowledgeReview) =>
      unwrap(
        await apiClient.PATCH(
          "/v1/workspaces/{workspace_id}/sources/{source_id}/knowledge/{item_id}",
          {
            params: {
              path: { workspace_id: workspaceId, source_id: sourceId, item_id: item.id },
            },
            body: patch,
          },
        ),
      ),
    onMutate: async ({ item, patch }) => {
      const key = knowledgeItemsQueryKey(workspaceId, sourceId, item.module_key);
      await queryClient.cancelQueries({ queryKey: key });
      const previous = queryClient.getQueryData<KnowledgeItem[]>(key);
      queryClient.setQueryData<KnowledgeItem[]>(key, (items) =>
        replaceItem(items, reviewedItem(item, patch)),
      );
      return { key, previous };
    },
    onError: (_error, _review, context) => {
      if (context !== undefined) {
        queryClient.setQueryData(context.key, context.previous);
        // The item may be gone (404) or changed by someone else: read the module again.
        void queryClient.invalidateQueries({ queryKey: context.key });
      }
    },
    onSuccess: (saved, _review, context) => {
      queryClient.setQueryData<KnowledgeItem[]>(context.key, (items) => replaceItem(items, saved));
    },
  });
}

/** Name of the zip when the answer has no usable `Content-Disposition`. */
function fallbackFilename(module: string | null): string {
  return module === null ? "knowledge.zip" : `${module}.zip`;
}

/**
 * `GET .../knowledge/export?module=` (any member): the zip of `.md` files, saved by the browser
 * under the name of `Content-Disposition`. Resolves with that name; 404 `module_not_found`.
 */
export function useExportKnowledge(workspaceId: string, sourceId: string) {
  return useMutation({
    mutationFn: async (module: string | null) => {
      const result = await apiClient.GET(
        "/v1/workspaces/{workspace_id}/sources/{source_id}/knowledge/export",
        {
          params: {
            path: { workspace_id: workspaceId, source_id: sourceId },
            query: { module: module ?? undefined },
          },
          parseAs: "blob",
        },
      );
      const blob = unwrap(result);
      const filename =
        attachmentFilename(result.response.headers.get("Content-Disposition")) ??
        fallbackFilename(module);
      saveBlob(blob, filename);
      return filename;
    },
  });
}
