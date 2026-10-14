import { describe, expect, it } from "vitest";

import {
  conversationSearchParams,
  hasConversationFilters,
  parseConversationSearch,
  toConversationsQuery,
  toCreationPeriod,
} from "./conversationFilters";

const PRODUCT = "00000000-0000-4000-8000-0000000000f1";
const USER = "00000000-0000-4000-8000-000000000101";
const WIDGET = "00000000-0000-4000-8000-0000000000b1";

describe("conversationFilters", () => {
  it("test_parse_conversation_search_reads_every_filter", () => {
    const params = new URLSearchParams(
      `product=${PRODUCT}&level=support&user=${USER}&channel=widget&widget=${WIDGET}` +
        "&from=2026-10-01&to=2026-10-31" +
        "&negative=1&offset=50",
    );

    expect(parseConversationSearch(params)).toEqual({
      filters: {
        product: PRODUCT,
        level: "support",
        user: USER,
        channel: "widget",
        widget: WIDGET,
        from: "2026-10-01",
        to: "2026-10-31",
        negative: true,
      },
      offset: 50,
    });
  });

  it("test_parse_conversation_search_drops_values_the_api_refuses", () => {
    const params = new URLSearchParams(
      "product=x&level=admin&user=ana&channel=slack&widget=site&from=ontem&to=2026-02-30&negative=sim",
    );

    expect(parseConversationSearch(params)).toEqual({
      filters: {
        product: undefined,
        level: undefined,
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
      filters: {
        product: PRODUCT,
        level: "end_user" as const,
        from: "2026-10-01",
        negative: true as const,
      },
      offset: 50,
    };

    const params = conversationSearchParams(search);

    expect(params.toString()).toBe(
      `product=${PRODUCT}&level=end_user&from=2026-10-01&negative=1&offset=50`,
    );
    expect(parseConversationSearch(params).filters).toMatchObject(search.filters);
    expect(conversationSearchParams({ filters: { user: "" }, offset: 0 }).toString()).toBe("");
  });

  it("test_to_conversations_query_turns_days_into_half_open_utc_period", () => {
    const query = toConversationsQuery(
      {
        filters: {
          product: PRODUCT,
          level: "product_dev",
          user: USER,
          channel: "panel",
          widget: WIDGET,
          from: "2026-10-01",
          to: "2026-10-31",
          negative: true,
        },
        offset: 50,
      },
      50,
    );

    expect(query).toEqual({
      productId: PRODUCT,
      level: "product_dev",
      userId: USER,
      channel: "panel",
      widgetId: WIDGET,
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
    expect(hasConversationFilters({ level: "support" })).toBe(true);
  });
});
