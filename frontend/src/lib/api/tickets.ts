import { useMutation } from "@tanstack/react-query";

import { apiClient, unwrap } from "./client";
import type { components } from "./schema.gen";
import { useRefreshSources } from "./sources";

export type IngestToken = components["schemas"]["IngestTokenOut"];
export type TicketIn = components["schemas"]["TicketIn"];
export type TicketPreview = components["schemas"]["TicketPreviewOut"];
export type TicketUploadReport = components["schemas"]["TicketUploadOut"];
export type TicketUploadError = components["schemas"]["TicketUploadError"];

/**
 * `POST .../sources/{source_id}/ingest-token` (201, owner or admin): issues the source's send
 * token, or replaces the current one, which stops working at once. The whole token comes only in
 * this answer; the server keeps its prefix and hash. Nothing cached changes.
 */
export function useRotateIngestToken(workspaceId: string) {
  return useMutation({
    mutationFn: async (sourceId: string) =>
      unwrap(
        await apiClient.POST("/v1/workspaces/{workspace_id}/sources/{source_id}/ingest-token", {
          params: { path: { workspace_id: workspaceId, source_id: sourceId } },
        }),
      ),
  });
}

export interface TicketUpload {
  sourceId: string;
  file: File;
}

/**
 * `POST .../tickets/upload` (editor): a `.json` or `.jsonl` file as `multipart/form-data`,
 * processed synchronously; 200 with the counts and the rejected items. Whole-file errors: 422
 * `upload_format_unsupported`, `upload_invalid_json`, `upload_empty`; 413 `payload_too_large`;
 * 409 `source_inactive`. Queued items start a run, so the source and its runs are reloaded.
 */
export function useUploadTickets(workspaceId: string) {
  const refresh = useRefreshSources(workspaceId);
  return useMutation({
    mutationFn: async ({ sourceId, file }: TicketUpload) => {
      const form = new FormData();
      form.append("file", file, file.name);
      return unwrap(
        await apiClient.POST("/v1/workspaces/{workspace_id}/sources/{source_id}/tickets/upload", {
          params: { path: { workspace_id: workspaceId, source_id: sourceId } },
          // The generated type describes the multipart field as a string; the real body is the
          // form built above (openapi-fetch sends a FormData as is, with its boundary).
          body: { file: "" },
          bodySerializer: () => form,
        }),
      );
    },
    onSuccess: refresh,
  });
}

export interface TicketPreviewRequest {
  sourceId: string;
  /** The pasted ticket; the server validates it as an API upsert. */
  ticket: TicketIn;
}

/**
 * `POST .../tickets/preview` (editor): the Markdown the index would get for `ticket` with the
 * source's current settings, and the anonymization markers it applied. Writes nothing. 422
 * `validation_error` (problems in `details`) or `ticket_too_large`; 413 `payload_too_large`.
 */
export function usePreviewTicket(workspaceId: string) {
  return useMutation({
    mutationFn: async ({ sourceId, ticket }: TicketPreviewRequest) =>
      unwrap(
        await apiClient.POST("/v1/workspaces/{workspace_id}/sources/{source_id}/tickets/preview", {
          params: { path: { workspace_id: workspaceId, source_id: sourceId } },
          body: { ticket },
        }),
      ),
  });
}
