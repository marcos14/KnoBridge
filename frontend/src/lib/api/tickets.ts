import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient, unwrap } from "./client";
import type { components } from "./schema.gen";
import { sourceQueryKey, useRefreshSources } from "./sources";

export type IngestToken = components["schemas"]["IngestTokenOut"];
export type TicketsSummary = components["schemas"]["TicketsSummaryOut"];
export type TicketsInboxCounts = components["schemas"]["TicketsInboxCounts"];
export type TicketIn = components["schemas"]["TicketIn"];
export type TicketPreview = components["schemas"]["TicketPreviewOut"];
export type TicketUploadReport = components["schemas"]["TicketUploadOut"];
export type TicketUploadError = components["schemas"]["TicketUploadError"];
export type CardIn = components["schemas"]["CardIn"];
export type CardPreview = components["schemas"]["CardPreviewOut"];
export type CardStatus = components["schemas"]["CardStatus"];

/**
 * The kinds of source that receive their items by push, with a send token, an upload and a
 * preview (`docs/specs/chamados.md`; cards follow the same path, `docs/specs/cards.md`). The
 * summary, the upload and the answers are the same for both; only the routes and the preview's
 * item differ.
 */
export type PushSourceKind = "tickets" | "cards";

export function isPushSourceKind(kind: string): kind is PushSourceKind {
  return kind === "tickets" || kind === "cards";
}

/** A push source as the hooks need it: its id and its kind, which picks the routes. */
export interface PushSourceRef {
  id: string;
  kind: PushSourceKind;
}

/**
 * Under the source's key, so whatever reloads the source (an upload, a sync) reloads it too.
 */
export function ingestSummaryQueryKey(workspaceId: string, sourceId: string) {
  return [...sourceQueryKey(workspaceId, sourceId), "ingest-summary"] as const;
}

async function fetchSummary(workspaceId: string, source: PushSourceRef, signal: AbortSignal) {
  const path = { workspace_id: workspaceId, source_id: source.id };
  return unwrap(
    source.kind === "cards"
      ? await apiClient.GET("/v1/workspaces/{workspace_id}/sources/{source_id}/cards/summary", {
          params: { path },
          signal,
        })
      : await apiClient.GET("/v1/workspaces/{workspace_id}/sources/{source_id}/tickets/summary", {
          params: { path },
          signal,
        }),
  );
}

/**
 * `GET .../sources/{source_id}/{tickets|cards}/summary` (any member): the inbox counts by state,
 * the pending entries that failed, the last item received and the prefix and date of the current
 * send token. 404 `source_not_found`.
 */
export function useIngestSummary(workspaceId: string, source: PushSourceRef) {
  return useQuery({
    queryKey: ingestSummaryQueryKey(workspaceId, source.id),
    queryFn: ({ signal }) => fetchSummary(workspaceId, source, signal),
  });
}

/**
 * `POST .../sources/{source_id}/ingest-token` (201, owner or admin), the same for both kinds:
 * issues the source's send token, or replaces the current one, which stops working at once. The
 * whole token comes only in this answer; the server keeps its prefix and hash, so the summary
 * (prefix and date) is reloaded.
 */
export function useRotateIngestToken(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (sourceId: string) =>
      unwrap(
        await apiClient.POST("/v1/workspaces/{workspace_id}/sources/{source_id}/ingest-token", {
          params: { path: { workspace_id: workspaceId, source_id: sourceId } },
        }),
      ),
    onSuccess: (_, sourceId) =>
      queryClient.invalidateQueries({ queryKey: ingestSummaryQueryKey(workspaceId, sourceId) }),
  });
}

export interface IngestUpload {
  source: PushSourceRef;
  file: File;
}

/**
 * `POST .../{tickets|cards}/upload` (editor): a `.json` or `.jsonl` file as
 * `multipart/form-data`, processed synchronously; 200 with the counts and the rejected items.
 * Whole-file errors: 422 `upload_format_unsupported`, `upload_invalid_json`, `upload_empty`; 413
 * `payload_too_large`; 409 `source_inactive`. Queued items start a run, so the source and its
 * runs are reloaded.
 */
export function useUploadIngestFile(workspaceId: string) {
  const refresh = useRefreshSources(workspaceId);
  return useMutation({
    mutationFn: async ({ source, file }: IngestUpload) => {
      const form = new FormData();
      form.append("file", file, file.name);
      const path = { workspace_id: workspaceId, source_id: source.id };
      // The generated type describes the multipart field as a string; the real body is the form
      // built above (openapi-fetch sends a FormData as is, with its boundary).
      const multipart = { body: { file: "" }, bodySerializer: () => form };
      return unwrap(
        source.kind === "cards"
          ? await apiClient.POST("/v1/workspaces/{workspace_id}/sources/{source_id}/cards/upload", {
              params: { path },
              ...multipart,
            })
          : await apiClient.POST(
              "/v1/workspaces/{workspace_id}/sources/{source_id}/tickets/upload",
              { params: { path }, ...multipart },
            ),
      );
    },
    onSuccess: refresh,
  });
}

/** The pasted item of a preview, sent as `{ticket}` or `{card}` by the source's kind. */
export type PreviewItem = { kind: "tickets"; ticket: TicketIn } | { kind: "cards"; card: CardIn };

export interface PreviewRequest {
  sourceId: string;
  item: PreviewItem;
}

/** The preview's answer; a card's says whether comments are in (`include_comments`). */
export type IngestPreview = TicketPreview | CardPreview;

/**
 * `POST .../{tickets|cards}/preview` (editor): the Markdown the index would get for the item with
 * the source's current settings, and the anonymization markers it applied. Writes nothing. 422
 * `validation_error` (problems in `details`), `ticket_too_large` or `card_too_large`; 413
 * `payload_too_large`.
 */
export function usePreviewIngestItem(workspaceId: string) {
  return useMutation({
    mutationFn: async ({ sourceId, item }: PreviewRequest): Promise<IngestPreview> => {
      const path = { workspace_id: workspaceId, source_id: sourceId };
      if (item.kind === "cards") {
        return unwrap(
          await apiClient.POST("/v1/workspaces/{workspace_id}/sources/{source_id}/cards/preview", {
            params: { path },
            body: { card: item.card },
          }),
        );
      }
      return unwrap(
        await apiClient.POST("/v1/workspaces/{workspace_id}/sources/{source_id}/tickets/preview", {
          params: { path },
          body: { ticket: item.ticket },
        }),
      );
    },
  });
}
