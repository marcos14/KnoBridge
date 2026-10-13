import { describe, expect, it } from "vitest";

import {
  conversationSearchParams,
  hasConversationFilters,
  parseConversationSearch,
  toConversationsQuery,
  toCreationPeriod,
} from "./conversationFilters";

const ASSISTANT = "00000000-0000-4000-8000-0000000000f1";
const USER = "00000000-0000-4000-8000-000000000101";

describe("conversationFilters", () => {
  it("test_parse_conversation_search_reads_every_filter", () => {
    const params = new URLSearchParams(
      `assistant=${ASSISTANT}&user=${USER}&channel=api&from=2026-10-01&to=2026-10-31&negative=1` +
        "&offset=50",
    );

    expect(parseConversationSearch(params)).toEqual({
      filters: {
        assistant: ASSISTANT,
        user: USER,
        channel: "api",
        from: "2026-10-01",
        to: "2026-10-31",
        negative: true,
      },
      offset: 50,
    });
  });

  it("test_parse_conversation_search_drops_values_the_api_refuses", () => {
    const params = new URLSearchParams(
      "assistant=x&user=ana&channel=slack&from=ontem&to=2026-02-30&negative=sim",
    );

    expect(parseConversationSearch(params)).toEqual({
      filters: {
        assistant: undefined,
        user: undefined,
        channel: undefined,
        from: undefined,
        to: undefined,
        negative: undefined,
      },
      offset: 0,
    });
  });

  it("test_conversation_search_params_round_trip_and_skip_empty", () => {
    const search = {
      filters: { assistant: ASSISTANT, from: "2026-10-01", negative: true as const },
      offset: 50,
    };

    const params = conversationSearchParams(search);

    expect(params.toString()).toBe(`assistant=${ASSISTANT}&from=2026-10-01&negative=1&offset=50`);
    expect(parseConversationSearch(params).filters).toMatchObject(search.filters);
    expect(conversationSearchParams({ filters: { user: "" }, offset: 0 }).toString()).toBe("");
  });

  it("test_to_conversations_query_turns_days_into_half_open_utc_period", () => {
    const query = toConversationsQuery(
      {
        filters: {
          user: USER,
          channel: "panel",
          from: "2026-10-01",
          to: "2026-10-31",
          negative: true,
        },
        offset: 50,
      },
      50,
    );

    expect(query).toEqual({
      assistantId: undefined,
      userId: USER,
      channel: "panel",
      createdFrom: new Date(2026, 9, 1).toISOString(),
      createdTo: new Date(2026, 10, 1).toISOString(),
      negativeFeedback: true,
      limit: 50,
      offset: 50,
    });
  });

  it("test_to_creation_period_without_days_is_open", () => {
    expect(toCreationPeriod({})).toEqual({ createdFrom: undefined, createdTo: undefined });
  });

  it("test_has_conversation_filters", () => {
    expect(hasConversationFilters({})).toBe(false);
    expect(hasConversationFilters({ negative: true })).toBe(true);
    expect(hasConversationFilters({ channel: "api" })).toBe(true);
  });
});
