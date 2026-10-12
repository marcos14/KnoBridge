import { http, HttpResponse } from "msw";

import type {
  ConversationStats,
  WorkspaceConversation,
  WorkspaceConversationDetail,
} from "@/lib/api/workspaceConversations";

import {
  makeConversationStats,
  makeWorkspaceConversationDetail,
  makeWorkspaceConversations,
} from "../factories";
import { apiErrorResponse } from "./errors";
import { page } from "./page";

const LIST = "*/v1/workspaces/:workspaceId/admin/conversations";
const STATS = "*/v1/workspaces/:workspaceId/admin/conversations/stats";
const DETAIL = "*/v1/workspaces/:workspaceId/admin/conversations/:conversationId";

/** `stats` also matches DETAIL: a detail handler returns nothing for it, so the next one answers. */
const isStats = (conversationId: unknown) => conversationId === "stats";

/** GET .../admin/conversations listing `rows` (filters ignored), paged like the API. */
export function workspaceConversationsAs(
  rows: WorkspaceConversation[] = makeWorkspaceConversations(),
) {
  return http.get(LIST, ({ request }) => page(request, rows));
}

/** GET .../admin/conversations/stats answering `stats` (period ignored). */
export function conversationStatsAs(stats: ConversationStats = makeConversationStats()) {
  return http.get(STATS, () => HttpResponse.json<ConversationStats>(stats));
}

/** GET .../admin/conversations/{id}: `details` by id (404 for any other id). */
export function workspaceConversationAs(
  ...details: WorkspaceConversationDetail[]
): ReturnType<typeof http.get> {
  const known = details.length === 0 ? [makeWorkspaceConversationDetail()] : details;
  return http.get(DETAIL, ({ params }) => {
    if (isStats(params.conversationId)) {
      return undefined;
    }
    const detail = known.find((item) => item.id === params.conversationId);
    return detail === undefined
      ? apiErrorResponse(404, "not_found")
      : HttpResponse.json<WorkspaceConversationDetail>(detail);
  });
}

/**
 * The list and the stats answering `rows` and `stats`, keeping the query string of each request
 * (`listQueries`, `statsQueries`) to assert on the filters the screen sent.
 */
export function workspaceConversationsRecorder(
  rows: WorkspaceConversation[] = makeWorkspaceConversations(),
  stats: ConversationStats = makeConversationStats(),
) {
  const listQueries: URLSearchParams[] = [];
  const statsQueries: URLSearchParams[] = [];
  const handlers = [
    http.get(STATS, ({ request }) => {
      statsQueries.push(new URL(request.url).searchParams);
      return HttpResponse.json<ConversationStats>(stats);
    }),
    http.get(LIST, ({ request }) => {
      listQueries.push(new URL(request.url).searchParams);
      return page(request, rows);
    }),
  ];
  return { handlers, listQueries, statsQueries };
}

/** GET .../admin/conversations failing on the server (500). */
export const workspaceConversationsServerError = http.get(LIST, () =>
  apiErrorResponse(500, "internal_error"),
);

/** GET .../admin/conversations/stats failing on the server (500). */
export const conversationStatsServerError = http.get(STATS, () =>
  apiErrorResponse(500, "internal_error"),
);

/** GET .../admin/conversations/{id} failing on the server (500). */
export const workspaceConversationServerError = http.get(DETAIL, ({ params }) =>
  isStats(params.conversationId) ? undefined : apiErrorResponse(500, "internal_error"),
);

/** Default handlers: two conversations, the default stats and the default thread. */
export const workspaceConversationsHandlers = [
  conversationStatsAs(),
  workspaceConversationsAs(),
  workspaceConversationAs(),
];
