import { http, HttpResponse } from "msw";

import type {
  IngestToken,
  TicketPreview,
  TicketPreviewRequest,
  TicketsSummary,
  TicketUploadReport,
} from "@/lib/api/tickets";

import {
  makeIngestToken,
  makeTicketPreview,
  makeTicketsSummary,
  makeTicketUploadReport,
} from "../ticketFactories";
import { apiErrorResponse } from "./errors";

const TOKEN = "*/v1/workspaces/:workspaceId/sources/:sourceId/ingest-token";
const SUMMARY = "*/v1/workspaces/:workspaceId/sources/:sourceId/tickets/summary";
const UPLOAD = "*/v1/workspaces/:workspaceId/sources/:sourceId/tickets/upload";
const PREVIEW = "*/v1/workspaces/:workspaceId/sources/:sourceId/tickets/preview";

/** Ticket actions of a source, for `ticketActionFails`. */
export type TicketAction = "token" | "upload" | "preview";

const ACTION_PATHS: Record<TicketAction, string> = {
  token: TOKEN,
  upload: UPLOAD,
  preview: PREVIEW,
};

interface TicketStoreOptions {
  token?: IngestToken;
  report?: TicketUploadReport;
  preview?: TicketPreview;
  summary?: TicketsSummary;
}

/**
 * Whether a body is `multipart/form-data` with a `file` part. Only the part is checked: under
 * jsdom, Node's fetch does not recognize jsdom's `File` and sends it empty, named "blob", so a
 * test checks what the panel appended by spying on `FormData.prototype.append`.
 */
function hasFilePart(contentType: string, body: string): boolean {
  return contentType.startsWith("multipart/form-data") && body.includes('name="file"');
}

/**
 * Ticket routes of a tickets source that keep what was asked: `rotations` (source ids of each
 * token issued), `uploads` (source ids of each multipart upload with a `file` part) and `previews`
 * (each preview body). They answer with the options (defaults: `makeIngestToken`,
 * `makeTicketUploadReport`, `makeTicketPreview`). The summary starts as `options.summary`
 * (default `makeTicketsSummary()`) and follows each token issued (prefix and date); `summaryReads`
 * counts its reads.
 */
export function ticketStore(options: TicketStoreOptions = {}) {
  const rotations: string[] = [];
  const uploads: string[] = [];
  const previews: { sourceId: string; body: Omit<TicketPreviewRequest, "sourceId"> }[] = [];
  let summary = options.summary ?? makeTicketsSummary();
  let summaryReads = 0;
  const handlers = [
    http.get(SUMMARY, () => {
      summaryReads += 1;
      return HttpResponse.json<TicketsSummary>(summary);
    }),
    http.post(TOKEN, ({ params }) => {
      rotations.push(String(params.sourceId));
      const token = options.token ?? makeIngestToken();
      summary = {
        ...summary,
        token_prefix: token.token_prefix,
        token_created_at: token.created_at,
      };
      return HttpResponse.json<IngestToken>(token, { status: 201 });
    }),
    http.post(UPLOAD, async ({ params, request }) => {
      if (!hasFilePart(request.headers.get("content-type") ?? "", await request.text())) {
        return apiErrorResponse(422, "validation_error", [
          { loc: ["body", "file"], problem: "missing" },
        ]);
      }
      uploads.push(String(params.sourceId));
      return HttpResponse.json<TicketUploadReport>(options.report ?? makeTicketUploadReport());
    }),
    http.post(PREVIEW, async ({ params, request }) => {
      const body = (await request.json()) as Omit<TicketPreviewRequest, "sourceId">;
      previews.push({ sourceId: String(params.sourceId), body });
      return HttpResponse.json<TicketPreview>(options.preview ?? makeTicketPreview());
    }),
  ];
  return {
    handlers,
    rotations,
    uploads,
    previews,
    summaryReads: () => summaryReads,
  };
}

/** GET .../tickets/summary failing on the server (500). */
export const ticketsSummaryServerError = http.get(SUMMARY, () =>
  apiErrorResponse(500, "internal_error"),
);

/** A ticket action refused with `status`, `code` and optional `details`. */
export function ticketActionFails(
  action: TicketAction,
  status: number,
  code: string,
  details: unknown = null,
) {
  return http.post(ACTION_PATHS[action], () => apiErrorResponse(status, code, details));
}

/** Stateless defaults: the token, the upload report and the preview of `ticketFactories`. */
export const ticketsHandlers = ticketStore().handlers;
