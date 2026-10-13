/**
 * Filters of the conversations screen, kept in the URL query string so a filtered view can be
 * shared: `?assistant=<id>&user=<id>&channel=panel|api&from=YYYY-MM-DD&to=YYYY-MM-DD&negative=1
 * &offset=<n>`.
 */

import type {
  ConversationChannel,
  CreationPeriod,
  WorkspaceConversationsQuery,
} from "@/lib/api/workspaceConversations";
import { dayPeriod, validDay } from "@/lib/days";
import { parseOffset } from "@/lib/pagination";
import { isUuid } from "@/lib/uuid";

export interface ConversationFilters {
  assistant?: string;
  user?: string;
  /** Where the conversation happened: the panel or the public API (owned by a key). */
  channel?: ConversationChannel;
  /** First day of the creation period, inclusive (`YYYY-MM-DD`, local calendar). */
  from?: string;
  /** Last day of the creation period, inclusive. */
  to?: string;
  /** Only conversations with a thumbs down. */
  negative?: true;
}

/** The channels a conversation can come from, in the order the filter lists them. */
export const CONVERSATION_CHANNELS: readonly ConversationChannel[] = ["panel", "api"];

/** The channel named by `value`, or `undefined` when it names none. */
export function parseChannel(value: string | null): ConversationChannel | undefined {
  return CONVERSATION_CHANNELS.find((channel) => channel === value);
}

export interface ConversationSearch {
  filters: ConversationFilters;
  offset: number;
}

/**
 * Filters and offset read from the URL. Values the API would refuse (malformed id or day) are
 * dropped, so a hand-edited link still opens a listing.
 */
export function parseConversationSearch(params: URLSearchParams): ConversationSearch {
  const assistant = params.get("assistant");
  const user = params.get("user");
  return {
    filters: {
      assistant: isUuid(assistant) ? assistant : undefined,
      user: isUuid(user) ? user : undefined,
      channel: parseChannel(params.get("channel")),
      from: validDay(params.get("from")),
      to: validDay(params.get("to")),
      negative: params.get("negative") === "1" ? true : undefined,
    },
    offset: parseOffset(params.get("offset")),
  };
}

/** Query string of a filtered page; empty filters and the first page leave no trace. */
export function conversationSearchParams({ filters, offset }: ConversationSearch): URLSearchParams {
  const params = new URLSearchParams();
  const entries: [string, string | undefined][] = [
    ["assistant", filters.assistant],
    ["user", filters.user],
    ["channel", filters.channel],
    ["from", filters.from],
    ["to", filters.to],
    ["negative", filters.negative === true ? "1" : undefined],
  ];
  for (const [key, value] of entries) {
    if (value !== undefined && value !== "") {
      params.set(key, value);
    }
  }
  if (offset > 0) {
    params.set("offset", String(offset));
  }
  return params;
}

/** Creation period of the filters, as the API takes it (`[start of "from", day after "to")`). */
export function toCreationPeriod(filters: ConversationFilters): CreationPeriod {
  const { start, end } = dayPeriod(filters.from, filters.to);
  return { createdFrom: start, createdTo: end };
}

/** Query sent to the API for the filters and page. */
export function toConversationsQuery(
  { filters, offset }: ConversationSearch,
  limit: number,
): WorkspaceConversationsQuery {
  return {
    assistantId: filters.assistant,
    userId: filters.user,
    channel: filters.channel,
    ...toCreationPeriod(filters),
    negativeFeedback: filters.negative,
    limit,
    offset,
  };
}

/** Whether any filter is set (shows the "clear filters" button and the filtered empty state). */
export function hasConversationFilters(filters: ConversationFilters): boolean {
  return Object.values(filters).some((value) => value !== undefined);
}
