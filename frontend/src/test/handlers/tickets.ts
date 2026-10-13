import { http, HttpResponse } from "msw";

import type {
  CardPreview,
  IngestToken,
  PushSourceKind,
  TicketPreview,
  TicketsSummary,
  TicketUploadReport,
} from "@/lib/api/tickets";

import {
  makeCardPreview,
  makeIngestToken,
  makeTicketPreview,
  makeTicketsSummary,
  makeTicketUploadReport,
} from "../ticketFactories";
import { apiErrorResponse } from "./errors";

const KINDS: readonly PushSourceKind[] = ["tickets", "cards"];
const TOKEN = "*/v1/workspaces/:workspaceId/sources/:sourceId/ingest-token";
const route = (kind: PushSourceKind, action: string) =>
  `*/v1/workspaces/:workspaceId/sources/:sourceId/${kind}/${action}`;

/** Push actions of a source, for `ticketActionFails`. */
export type TicketAction = "token" | "upload" | "preview";

interface TicketStoreOptions {
  token?: IngestToken;
  report?: TicketUploadReport;
  preview?: TicketPreview;
  cardPreview?: CardPreview;
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
 * Push routes of a tickets or cards source (`.../tickets/*` and `.../cards/*`, and the shared
 * token) that keep what was asked: `rotations` (source ids of each token issued), `uploads`
 * (source ids of each multipart upload with a `file` part), `uploadKinds` (the route's kind of
 * each upload) and `previews` (each preview, with the kind and body). They answer with the options
 * (defaults: `makeIngestToken`, `makeTicketUploadReport`, `makeTicketPreview` and
 * `makeCardPreview`). The summary starts as `options.summary` (default `makeTicketsSummary()`)
 * and follows each token issued (prefix and date); `summaryReads` counts its reads.
 */
export function ticketStore(options: TicketStoreOptions = {}) {
  const rotations: string[] = [];
  const uploads: string[] = [];
  const uploadKinds: PushSourceKind[] = [];
  const previews: { sourceId: string; kind: PushSourceKind; body: unknown }[] = [];
  let summary = options.summary ?? makeTicketsSummary();
  let summaryReads = 0;
  const handlers = [
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
    ...KINDS.flatMap((kind) => [
      http.get(route(kind, "summary"), () => {
        summaryReads += 1;
        return HttpResponse.json<TicketsSummary>(summary);
      }),
      http.post(route(kind, "upload"), async ({ params, request }) => {
        if (!hasFilePart(request.headers.get("content-type") ?? "", await request.text())) {
          return apiErrorResponse(422, "validation_error", [
            { loc: ["body", "file"], problem: "missing" },
          ]);
        }
        uploads.push(String(params.sourceId));
        uploadKinds.push(kind);
        return HttpResponse.json<TicketUploadReport>(options.report ?? makeTicketUploadReport());
      }),
      http.post(route(kind, "preview"), async ({ params, request }) => {
        previews.push({ sourceId: String(params.sourceId), kind, body: await request.json() });
        return HttpResponse.json<CardPreview | TicketPreview>(
          kind === "cards"
            ? (options.cardPreview ?? makeCardPreview())
            : (options.preview ?? makeTicketPreview()),
        );
      }),
    ]),
  ];
  return {
    handlers,
    rotations,
    uploads,
    uploadKinds,
    previews,
    summaryReads: () => summaryReads,
  };
}

/** GET .../{tickets|cards}/summary failing on the server (500). */
export const ticketsSummaryServerError = KINDS.map((kind) =>
  http.get(route(kind, "summary"), () => apiErrorResponse(500, "internal_error")),
);

/** A push action (of both kinds) refused with `status`, `code` and optional `details`. */
export function ticketActionFails(
  action: TicketAction,
  status: number,
  code: string,
  details: unknown = null,
) {
  const paths = action === "token" ? [TOKEN] : KINDS.map((kind) => route(kind, action));
  return paths.map((path) => http.post(path, () => apiErrorResponse(status, code, details)));
}

/** Stateless defaults: the token, the upload report and the previews of `ticketFactories`. */
export const ticketsHandlers = ticketStore().handlers;
